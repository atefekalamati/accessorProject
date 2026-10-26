"""POST /payments/init: start, resume, supersede, gateway failure (PAY-02, ADR-051)."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from conftest import Catalog
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from test_orders_cancel import _cancel, _expire_now, _placed
from test_orders_create import (
    API,
    Buyer,
    MakeBuyer,
    _count,
    _error,
    _orders_go_first,
    buyer,
    codes,
    methods,
    shopper,
)

from app.core.config import Environment
from app.core.time import utc_now
from app.db.models import (
    AuditLog,
    FakeGatewaySession,
    Order,
    Payment,
)
from app.modules.payments.gateways.base import (
    GatewayRequest,
    GatewayUnavailable,
)
from app.modules.payments.gateways.fake import FakeGateway

pytestmark = pytest.mark.integration

__all__ = ["_orders_go_first", "buyer", "codes", "methods", "shopper"]  # shared fixtures

INIT = f"{API}/payments/init"


def _app(client: AsyncClient) -> FastAPI:
    transport = client._transport
    assert isinstance(transport, ASGITransport)
    app = transport.app
    assert isinstance(app, FastAPI)
    return app


def _fake(client: AsyncClient) -> FakeGateway:
    app = _app(client)
    gateway = getattr(app.state, "payment_gateway", None)
    if gateway is None:
        from app.modules.payments.gateways import build_payment_gateway

        gateway = build_payment_gateway(app.state.settings, app.state.db_engine)
        app.state.payment_gateway = gateway
    assert isinstance(gateway, FakeGateway)
    return gateway


async def _init(ready: Buyer, order_id: UUID, key: str | None = None) -> Response:
    headers = ready.account.headers | {"Idempotency-Key": key or str(uuid4())}
    return await ready.client.post(INIT, json={"order_id": str(order_id)}, headers=headers)


async def _payments(engine: AsyncEngine, order_id: UUID) -> list[Payment]:
    async with AsyncSession(engine) as session:
        return list(
            await session.scalars(
                select(Payment).where(Payment.order_id == order_id).order_by(Payment.created_at)
            )
        )


async def _order(engine: AsyncEngine, order_id: UUID) -> Order:
    async with AsyncSession(engine) as session:
        order = await session.get(Order, order_id)
        assert order is not None
        return order


async def _ready_order(catalog: Catalog, buyer: MakeBuyer) -> tuple[Buyer, UUID]:
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0), base_price=100_000)
    ready = await buyer((variant, 1))
    return ready, await _placed(ready)


async def _expire_session(engine: AsyncEngine, payment: Payment) -> None:
    """The gateway session ended (the customer took too long)."""
    past = utc_now() - timedelta(seconds=1)
    async with AsyncSession(engine) as session, session.begin():
        await session.execute(
            update(Payment).where(Payment.id == payment.id).values(gateway_expires_at=past)
        )
        await session.execute(
            update(FakeGatewaySession)
            .where(FakeGatewaySession.reference == payment.gateway_reference)
            .values(expires_at=past)
        )


# --- start ---------------------------------------------------------------------------


async def test_init_starts_a_payment_of_the_order_total(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    ready, order_id = await _ready_order(catalog, buyer)
    order = await _order(db_engine, order_id)

    response = await _init(ready, order_id)

    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert (body["amount"], body["currency"], body["order_number"]) == (
        order.grand_total,
        "TOMAN",
        order.order_number,
    )
    [payment] = await _payments(db_engine, order_id)
    assert (payment.status, payment.amount, payment.gateway) == (
        "pending",
        order.grand_total,
        "fake",
    )
    assert payment.redirect_url is not None
    assert body["redirect_url"] == payment.redirect_url
    assert payment.redirect_url.endswith(f"/api/v1/payments/fake/{payment.gateway_reference}")
    assert (await _order(db_engine, order_id)).payment_status == "pending"
    async with AsyncSession(db_engine) as session:
        fake = await session.get(FakeGatewaySession, payment.gateway_reference)
    assert fake is not None and fake.amount_rial == order.grand_total * 10  # rial at the edge
    assert (
        await _count(
            db_engine,
            AuditLog,
            AuditLog.entity_id == payment.id,
            AuditLog.action == "payment.created",
        )
        == 1
    )
    page = await ready.client.get(payment.redirect_url.removeprefix("http://localhost:8000"))
    assert page.json() == {"reference": payment.gateway_reference, "status": "pending"}


async def test_init_replays_the_same_key_and_refuses_a_different_body(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    ready, order_id = await _ready_order(catalog, buyer)
    key = str(uuid4())

    first, again = await _init(ready, order_id, key), await _init(ready, order_id, key)

    assert first.status_code == again.status_code == 201
    assert first.json() == again.json()
    assert len(await _payments(db_engine, order_id)) == 1
    other_ready, other_order = await _ready_order(catalog, buyer)
    reused = await ready.client.post(
        INIT,
        json={"order_id": str(other_order)},
        headers=ready.account.headers | {"Idempotency-Key": key},
    )
    _error(reused, 422, "IDEMPOTENCY_KEY_REUSED")


async def test_init_errors(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    ready, order_id = await _ready_order(catalog, buyer)
    other, _ = await _ready_order(catalog, buyer)
    body = {"order_id": str(order_id)}
    key = {"Idempotency-Key": str(uuid4())}

    _error(await auth_client.post(INIT, json=body), 401, "UNAUTHORIZED")
    _error(await auth_client.post(f"{INIT}?x=1", json=body), 401, "UNAUTHORIZED")
    _error(
        await auth_client.post(INIT, json=body, headers=ready.account.headers),
        400,
        "VALIDATION_ERROR",
    )
    # The amount always comes from the order: a client amount is refused.
    with_amount = body | {"amount": 1}
    _error(
        await auth_client.post(INIT, json=with_amount, headers=ready.account.headers | key),
        400,
        "VALIDATION_ERROR",
    )
    for response in (await _init(other, order_id), await _init(ready, uuid4())):
        _error(response, 404, "NOT_FOUND")
    assert await _payments(db_engine, order_id) == []
    assert (await _cancel(ready, order_id)).status_code == 200
    _error(await _init(ready, order_id), 422, "INVALID_STATE_TRANSITION", "order_not_payable")


async def test_an_expired_reservation_cancels_the_order(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    ready, order_id = await _ready_order(catalog, buyer)
    await _expire_now(db_engine, order_id)

    _error(await _init(ready, order_id), 409, "RESERVATION_EXPIRED", "reservation_expired")

    order = await _order(db_engine, order_id)
    assert (order.status, order.cancel_reason) == ("cancelled", "expired")
    assert await _payments(db_engine, order_id) == []


async def test_too_little_time_left_is_refused_without_cancelling(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    from app.db.models import InventoryReservation

    ready, order_id = await _ready_order(catalog, buyer)
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            update(InventoryReservation)
            .where(InventoryReservation.order_id == order_id)
            .values(expires_at=utc_now() + timedelta(seconds=30))
        )

    _error(await _init(ready, order_id), 409, "RESERVATION_EXPIRED", "too_late")

    assert (await _order(db_engine, order_id)).status == "pending_payment"


# --- an existing pending payment ----------------------------------------------------


async def test_init_again_resumes_a_live_gateway_session(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    ready, order_id = await _ready_order(catalog, buyer)
    first = await _init(ready, order_id)

    again = await _init(ready, order_id)  # another key: the customer came back

    assert again.status_code == 201, again.text
    assert again.json()["payment_id"] == first.json()["payment_id"]
    assert again.json()["redirect_url"] == first.json()["redirect_url"]
    assert len(await _payments(db_engine, order_id)) == 1


async def test_init_again_supersedes_an_expired_gateway_session(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    ready, order_id = await _ready_order(catalog, buyer)
    assert (await _init(ready, order_id)).status_code == 201
    [old] = await _payments(db_engine, order_id)
    await _expire_session(db_engine, old)

    again = await _init(ready, order_id)

    assert again.status_code == 201, again.text
    closed, new = await _payments(db_engine, order_id)
    assert (closed.id, closed.status, closed.failure_reason) == (
        old.id,
        "failed",
        "session_expired",
    )
    assert (new.status, str(new.id)) == ("pending", again.json()["payment_id"])
    assert (await _order(db_engine, order_id)).payment_status == "pending"


async def test_a_superseded_session_that_was_paid_is_applied(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    ready, order_id = await _ready_order(catalog, buyer)
    assert (await _init(ready, order_id)).status_code == 201
    [old] = await _payments(db_engine, order_id)
    assert await _fake(auth_client).complete(old.gateway_reference or "", paid=True)
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            update(Payment)
            .where(Payment.id == old.id)
            .values(gateway_expires_at=utc_now() - timedelta(seconds=1))
        )

    # Its money arrived after all: init applies it like the callback would (PAY-03).
    _error(await _init(ready, order_id), 422, "INVALID_STATE_TRANSITION", "order_not_payable")

    [paid] = await _payments(db_engine, order_id)
    assert paid.status == "paid"
    order = await _order(db_engine, order_id)
    assert (order.status, order.payment_status) == ("confirmed", "paid")


async def test_a_request_in_flight_is_409_until_it_is_stale(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    ready, order_id = await _ready_order(catalog, buyer)
    async with AsyncSession(db_engine) as session, session.begin():
        order = await session.get(Order, order_id)
        assert order is not None
        session.add(
            Payment(
                order_id=order_id, gateway="fake", idempotency_key="k", amount=order.grand_total
            )
        )
        order.payment_status = "pending"

    _error(await _init(ready, order_id), 409, "PAYMENT_IN_PROGRESS", "request_in_flight")

    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            update(Payment)
            .where(Payment.order_id == order_id)
            .values(created_at=utc_now() - timedelta(hours=1))
        )
    again = await _init(ready, order_id)
    assert again.status_code == 201, again.text
    lost, new = await _payments(db_engine, order_id)
    assert (lost.status, lost.failure_reason, new.status) == ("failed", "request_lost", "pending")


# --- the gateway ---------------------------------------------------------------------


class _DownGateway(FakeGateway):
    async def request(self, *, payment_id: UUID, amount: int, callback_url: str) -> GatewayRequest:
        raise GatewayUnavailable("connection refused")


async def test_a_gateway_that_does_not_answer_closes_the_payment(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    ready, order_id = await _ready_order(catalog, buyer)
    app = _app(auth_client)
    fake = _fake(auth_client)
    app.state.payment_gateway = _DownGateway(db_engine, base_url="http://x", session_seconds=900)
    try:
        _error(await _init(ready, order_id), 503, "PAYMENT_GATEWAY_UNAVAILABLE")
    finally:
        app.state.payment_gateway = fake

    [failed] = await _payments(db_engine, order_id)
    assert (failed.status, failed.failure_reason) == ("failed", "gateway_error")
    assert (await _order(db_engine, order_id)).payment_status == "failed"
    retry = await _init(ready, order_id)  # failed → pending: the order stays payable
    assert retry.status_code == 201, retry.text
    assert (await _order(db_engine, order_id)).payment_status == "pending"


async def test_production_has_no_gateway_yet(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer
) -> None:
    ready, order_id = await _ready_order(catalog, buyer)
    app = _app(auth_client)
    saved_settings, saved_gateway = app.state.settings, getattr(app.state, "payment_gateway", None)
    app.state.settings = saved_settings.model_copy(update={"environment": Environment.PRODUCTION})
    app.state.payment_gateway = None
    try:
        _error(await _init(ready, order_id), 503, "PAYMENT_GATEWAY_UNAVAILABLE")
    finally:
        app.state.settings, app.state.payment_gateway = saved_settings, saved_gateway


async def test_the_fake_page_is_only_for_the_fake_gateway(
    auth_client: AsyncClient, settings: Any
) -> None:
    from app.main import create_app

    _error(await auth_client.get(f"{API}/payments/fake/FAKE-none"), 404, "NOT_FOUND")
    unknown = await auth_client.post(
        f"{API}/payments/fake/FAKE-none/complete", json={"result": "paid"}
    )
    _error(unknown, 404, "NOT_FOUND")
    production = create_app(
        settings.model_copy(
            update={"environment": Environment.PRODUCTION, "otp_mock_enabled": False}
        )
    )
    assert not any("/payments/fake" in path for path in production.openapi()["paths"])
    assert any("/payments/fake" in path for path in _app(auth_client).openapi()["paths"])


# --- concurrency ---------------------------------------------------------------------


async def test_concurrent_inits_start_one_payment(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    ready, order_id = await _ready_order(catalog, buyer)
    key = str(uuid4())

    responses = await asyncio.gather(
        _init(ready, order_id),
        _init(ready, order_id),
        *(_init(ready, order_id, key) for _ in range(3)),
    )

    same_key = responses[2:]
    replays = [r.json() for r in same_key if r.status_code == 201]
    assert all(body == replays[0] for body in replays)  # JSONB may reorder keys
    statuses = [response.status_code for response in responses]
    assert set(statuses) <= {201, 409} and 201 in statuses, [r.text for r in responses]
    assert len(await _payments(db_engine, order_id)) == 1
    started = {
        response.json()["payment_id"] for response in responses if response.status_code == 201
    }
    assert len(started) == 1


async def test_init_racing_a_customer_cancel(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    ready, order_id = await _ready_order(catalog, buyer)

    started, cancelled = await asyncio.gather(_init(ready, order_id), _cancel(ready, order_id))

    order = await _order(db_engine, order_id)
    if cancelled.status_code == 200:
        # The cancel won: init then finds a cancelled order and starts nothing.
        assert order.status == "cancelled"
        _error(started, 422, "INVALID_STATE_TRANSITION", "order_not_payable")
        assert await _payments(db_engine, order_id) == []
    else:
        _error(cancelled, 409, "PAYMENT_IN_PROGRESS")
        assert started.status_code == 201
        assert order.status == "pending_payment"


async def test_init_racing_the_expiry_sweep(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    from app.modules.inventory.jobs import sweep_expired_reservations

    ready, order_id = await _ready_order(catalog, buyer)
    await _expire_now(db_engine, order_id)

    response, swept = await asyncio.gather(
        _init(ready, order_id), sweep_expired_reservations(db_engine)
    )

    _error(response, 409, "RESERVATION_EXPIRED")
    assert swept.failed == 0
    order = await _order(db_engine, order_id)
    assert (order.status, order.cancel_reason) == ("cancelled", "expired")


class _SlowGateway(FakeGateway):
    async def request(self, *, payment_id: UUID, amount: int, callback_url: str) -> GatewayRequest:
        await asyncio.sleep(5)
        raise AssertionError("the timeout should have fired")


class _BrokenGateway(FakeGateway):
    async def request(self, *, payment_id: UUID, amount: int, callback_url: str) -> GatewayRequest:
        raise ValueError("adapter bug")


@pytest.mark.parametrize("kind", ["slow", "broken"])
async def test_a_slow_or_broken_gateway_never_leaves_the_order_stuck(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    db_engine: AsyncEngine,
    kind: str,
) -> None:
    ready, order_id = await _ready_order(catalog, buyer)
    app = _app(auth_client)
    fake = _fake(auth_client)
    saved = app.state.settings
    app.state.settings = saved.model_copy(update={"payment_gateway_timeout_seconds": 0.2})
    gateway_type = _SlowGateway if kind == "slow" else _BrokenGateway
    app.state.payment_gateway = gateway_type(db_engine, base_url="http://x", session_seconds=900)
    try:
        if kind == "slow":
            _error(await _init(ready, order_id), 503, "PAYMENT_GATEWAY_UNAVAILABLE")
        else:
            with pytest.raises(ValueError, match="adapter bug"):
                await _init(ready, order_id)
    finally:
        app.state.settings, app.state.payment_gateway = saved, fake

    [failed] = await _payments(db_engine, order_id)
    assert (failed.status, failed.failure_reason) == ("failed", "gateway_error")
    assert (await _init(ready, order_id)).status_code == 201


async def test_a_superseded_session_the_gateway_still_holds_is_not_closed(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    ready, order_id = await _ready_order(catalog, buyer)
    assert (await _init(ready, order_id)).status_code == 201
    [old] = await _payments(db_engine, order_id)
    # Our record of the session ended, but the gateway still accepts it (verify: pending).
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            update(Payment)
            .where(Payment.id == old.id)
            .values(gateway_expires_at=utc_now() - timedelta(seconds=1))
        )

    _error(await _init(ready, order_id), 409, "PAYMENT_IN_PROGRESS", "session_open")

    [still] = await _payments(db_engine, order_id)
    assert still.status == "pending"


class _ExpiringGateway(FakeGateway):
    """Answers only after the order's reservation has ended."""

    async def request(self, *, payment_id: UUID, amount: int, callback_url: str) -> GatewayRequest:
        from app.db.models import InventoryReservation

        answer = await super().request(
            payment_id=payment_id, amount=amount, callback_url=callback_url
        )
        async with AsyncSession(self._engine) as session, session.begin():
            payment = await session.get(Payment, payment_id)
            assert payment is not None
            await session.execute(
                update(InventoryReservation)
                .where(InventoryReservation.order_id == payment.order_id)
                .values(expires_at=utc_now() - timedelta(seconds=1))
            )
        return answer


async def test_a_reservation_ending_during_the_gateway_call_closes_the_payment(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    ready, order_id = await _ready_order(catalog, buyer)
    app = _app(auth_client)
    fake = _fake(auth_client)
    app.state.payment_gateway = _ExpiringGateway(
        db_engine, base_url="http://x", session_seconds=900
    )
    try:
        _error(await _init(ready, order_id), 409, "RESERVATION_EXPIRED")
    finally:
        app.state.payment_gateway = fake

    [closed] = await _payments(db_engine, order_id)
    assert (closed.status, closed.failure_reason) == ("failed", "reservation_expired")
    assert closed.gateway_reference is not None  # the unused session is on record


async def test_a_resumed_session_replays_under_its_own_key(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    ready, order_id = await _ready_order(catalog, buyer)
    first = await _init(ready, order_id)
    key = str(uuid4())

    resumed, replayed = await _init(ready, order_id, key), await _init(ready, order_id, key)

    assert resumed.json() == replayed.json() == first.json()
    assert len(await _payments(db_engine, order_id)) == 1


async def test_an_expired_reservation_leaves_a_live_payment_for_its_callback(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    ready, order_id = await _ready_order(catalog, buyer)
    assert (await _init(ready, order_id)).status_code == 201
    await _expire_now(db_engine, order_id)

    _error(await _init(ready, order_id), 409, "RESERVATION_EXPIRED")

    order = await _order(db_engine, order_id)
    assert (order.status, order.payment_status) == ("cancelled", "pending")
    [payment] = await _payments(db_engine, order_id)
    # A late success becomes refund_required (D32, PAY-03); otherwise reconciliation closes it.
    assert payment.status == "pending"
