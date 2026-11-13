"""Reconciliation of pending payments: lost callbacks, lost requests, abandoned sessions
and event retention (PAY-04, ADR-049, ADR-051)."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from conftest import Catalog
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from test_orders_cancel import _placed, _reservation
from test_orders_create import (
    MakeBuyer,
    _orders_go_first,
    buyer,
    codes,
    methods,
    shopper,
)
from test_payments_callback import _callback, _complete, _order_ready, _started
from test_payments_init import _app, _fake, _init, _order, _payments

from app.core.config import Environment, Settings
from app.core.time import utc_now
from app.db.models import AuditLog, Cart, Order, Payment, PaymentEvent
from app.main import create_app
from app.modules.orders.cancel import order_advisory_lock
from app.modules.payments.gateways.base import GatewayUnavailable, VerifyOutcome, VerifyResult
from app.modules.payments.jobs import (
    JOB_LOCK_KEY,
    JOB_LOCK_NAMESPACE,
    ReconcileResult,
    reconcile_pending_payments,
)

pytestmark = pytest.mark.integration

__all__ = ["_orders_go_first", "buyer", "codes", "methods", "shopper"]  # shared fixtures

LATER = timedelta(minutes=10)  # past PAYMENT_PENDING_STALE_SECONDS (300)


async def _reconcile(client: AsyncClient, gateway: Any = None, **kwargs: Any) -> ReconcileResult:
    app = _app(client)
    return await reconcile_pending_payments(
        app.state.db_engine,
        gateway or _fake(client),
        app.state.settings,
        now=kwargs.pop("now", utc_now() + LATER),
        **kwargs,
    )


async def _status(engine: AsyncEngine, payment_id: UUID) -> tuple[str, str | None]:
    async with AsyncSession(engine) as session:
        payment = await session.get(Payment, payment_id)
        assert payment is not None
        return payment.status, payment.failure_reason


async def test_a_lost_callback_is_applied_by_reconciliation(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    _, ready = await _order_ready(catalog, buyer)
    order_id = await _placed(ready)
    payment = await _started(ready, order_id)
    await _complete(auth_client, payment)  # paid at the gateway; no callback ever comes

    early = await _reconcile(auth_client, now=utc_now())
    assert early.ran and await _status(db_engine, payment.id) == ("pending", None)  # not stale

    result = await _reconcile(auth_client)

    assert result.ran and result.applied >= 1 and result.failed == 0
    assert await _status(db_engine, payment.id) == ("paid", None)
    order = await _order(db_engine, order_id)
    assert (order.status, order.payment_status) == ("confirmed", "paid")
    assert (await _reservation(db_engine, order_id)).status == "committed"
    # The late callback afterwards changes nothing.
    assert (await _callback(auth_client, payment.gateway_reference)).json()["outcome"] == "success"
    # Same payment, so not reclassified as a duplicate needing a refund.
    assert await _status(db_engine, payment.id) == ("paid", None)


async def test_a_declined_payment_is_closed_and_one_still_at_the_gateway_is_left(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    _, ready = await _order_ready(catalog, buyer)
    declined_order = await _placed(ready)
    declined = await _started(ready, declined_order)
    await _complete(auth_client, declined, result="failed")
    _, other = await _order_ready(catalog, buyer)
    waiting_order = await _placed(other)
    waiting = await _started(other, waiting_order)
    # Still at the gateway with a live session (its own clock); a stale age alone is no reason.
    result = await _reconcile(auth_client, now=utc_now() + timedelta(minutes=6))

    assert result.failed == 0
    assert await _status(db_engine, declined.id) == ("failed", "declined")
    assert await _status(db_engine, waiting.id) == ("pending", None)


async def test_a_request_that_never_came_back_is_closed(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    _, ready = await _order_ready(catalog, buyer)
    order_id = await _placed(ready)
    async with AsyncSession(db_engine) as session, session.begin():
        order = await session.get(Order, order_id)
        assert order is not None
        lost = Payment(
            order_id=order_id, gateway="fake", idempotency_key="k", amount=order.grand_total
        )
        session.add(lost)
        await session.flush()
        payment_id = lost.id
        order.payment_status = "pending"

    result = await _reconcile(auth_client)

    assert result.closed >= 1
    assert await _status(db_engine, payment_id) == ("failed", "request_lost")
    assert (await _order(db_engine, order_id)).payment_status == "failed"
    assert (await _init(ready, order_id)).status_code == 201  # payable again


class _ForeverPending:
    """A gateway that keeps answering pending, even after the session ended."""

    name = "fake"

    async def verify(self, *, reference: str, amount: int) -> VerifyResult:
        return VerifyResult(VerifyOutcome.PENDING, raw={"reference": reference})


async def test_a_session_pending_long_after_it_ended_is_abandoned(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    _, ready = await _order_ready(catalog, buyer)
    order_id = await _placed(ready)
    payment = await _started(ready, order_id)
    assert payment.gateway_expires_at is not None

    soon = await _reconcile(auth_client, _ForeverPending(), now=payment.gateway_expires_at)
    assert soon.failed == 0 and await _status(db_engine, payment.id) == ("pending", None)

    late = payment.gateway_expires_at + timedelta(minutes=6)
    result = await _reconcile(auth_client, _ForeverPending(), now=late)

    assert result.closed >= 1
    assert await _status(db_engine, payment.id) == ("failed", "abandoned")


class _Down:
    name = "fake"

    async def verify(self, *, reference: str, amount: int) -> VerifyResult:
        raise GatewayUnavailable("timeout")


async def test_an_unreachable_gateway_changes_nothing(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    _, ready = await _order_ready(catalog, buyer)
    order_id = await _placed(ready)
    payment = await _started(ready, order_id)

    result = await _reconcile(auth_client, _Down())

    assert result.failed >= 1
    assert await _status(db_engine, payment.id) == ("pending", None)


async def test_a_busy_order_is_left_for_the_next_round(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    _, ready = await _order_ready(catalog, buyer)
    order_id = await _placed(ready)
    payment = await _started(ready, order_id)
    await _complete(auth_client, payment)

    async with AsyncSession(db_engine) as holder, holder.begin():
        await holder.execute(order_advisory_lock(order_id))
        busy = await _reconcile(auth_client)
        assert busy.failed == 0 and await _status(db_engine, payment.id) == ("pending", None)

    await _reconcile(auth_client)
    assert await _status(db_engine, payment.id) == ("paid", None)


async def test_one_runner_at_a_time(auth_client: AsyncClient, db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as other, other.begin():
        await other.execute(select(func.pg_advisory_xact_lock(JOB_LOCK_NAMESPACE, JOB_LOCK_KEY)))
        assert await _reconcile(auth_client) == ReconcileResult(ran=False)
    assert (await _reconcile(auth_client)).ran


async def test_reconciliation_racing_the_callback_applies_once(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    _, ready = await _order_ready(catalog, buyer)
    order_id = await _placed(ready)
    payment = await _started(ready, order_id)
    await _complete(auth_client, payment)

    callback, _ = await asyncio.gather(
        _callback(auth_client, payment.gateway_reference), _reconcile(auth_client)
    )
    await _reconcile(auth_client)  # whatever a busy lock skipped

    assert callback.status_code == 200
    assert await _status(db_engine, payment.id) == ("paid", None)
    async with AsyncSession(db_engine) as session:
        paid_audits = await session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.entity_id == payment.id, AuditLog.action == "payment.paid")
        )
    assert paid_audits == 1  # applied once
    [only] = await _payments(db_engine, order_id)
    assert only.paid_amount == only.amount


async def test_old_events_are_purged_and_recent_ones_kept(
    auth_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    old_ref, new_ref = f"FAKE-{uuid4().hex}", f"FAKE-{uuid4().hex}"
    async with AsyncSession(db_engine) as session, session.begin():
        session.add_all(
            [
                PaymentEvent(
                    gateway="fake", kind="callback", gateway_reference=old_ref, payload={}
                ),
                PaymentEvent(
                    gateway="fake", kind="callback", gateway_reference=new_ref, payload={}
                ),
            ]
        )
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            update(PaymentEvent)
            .where(PaymentEvent.gateway_reference == old_ref)
            .values(created_at=utc_now() - timedelta(days=91))
        )

    result = await _reconcile(auth_client, now=utc_now())

    assert result.purged_events >= 1
    async with AsyncSession(db_engine) as session:
        left = set(
            await session.scalars(
                select(PaymentEvent.gateway_reference).where(
                    PaymentEvent.gateway_reference.in_([old_ref, new_ref])
                )
            )
        )
    assert left == {new_ref}


async def test_lifespan_starts_and_stops_the_reconciler(settings: Settings) -> None:
    application = create_app(settings.model_copy(update={"payment_reconcile_seconds": 60}))
    async with application.router.lifespan_context(application):
        reconciler = application.state.payment_reconciler
        assert isinstance(reconciler, asyncio.Task) and not reconciler.done()
    assert reconciler.cancelled()


async def test_the_reconciler_fails_closed_in_production(settings: Settings) -> None:
    production = settings.model_copy(
        update={
            "environment": Environment.PRODUCTION,
            "otp_mock_enabled": False,
            "payment_reconcile_seconds": 60,
        }
    )
    application = create_app(production)
    with pytest.raises(RuntimeError, match="production"):
        async with application.router.lifespan_context(application):
            pass


async def _three_paid_orders(
    client: AsyncClient, catalog: Catalog, buyer: MakeBuyer
) -> list[Payment]:
    payments = []
    for _ in range(3):
        _, ready = await _order_ready(catalog, buyer)
        payment = await _started(ready, await _placed(ready))
        await _complete(client, payment)
        payments.append(payment)
    return payments


async def test_the_batch_cap_leaves_the_rest_for_the_next_round(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    payments = await _three_paid_orders(auth_client, catalog, buyer)
    # Older leftovers of this worker's database come first; settle them out of the way.
    await _reconcile(auth_client, now=utc_now() + timedelta(minutes=4))
    later = max(p.created_at for p in payments) + LATER

    first = await _reconcile(auth_client, batch_size=1, max_batches=2, now=later)

    statuses = [(await _status(db_engine, p.id))[0] for p in payments]
    assert first.applied == 2 and sorted(statuses) == ["paid", "paid", "pending"]
    await _reconcile(auth_client, now=later)
    assert [(await _status(db_engine, p.id))[0] for p in payments] == ["paid"] * 3


async def test_a_busy_cart_or_order_row_is_skipped_not_failed(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    _, ready = await _order_ready(catalog, buyer)
    order_id = await _placed(ready)
    payment = await _started(ready, order_id)
    await _complete(auth_client, payment)

    for held in (
        select(Cart).where(Cart.user_id == ready.account.id).with_for_update(),
        select(Order).where(Order.id == order_id).with_for_update(),
    ):
        async with AsyncSession(db_engine) as holder, holder.begin():
            await holder.execute(held)
            busy = await _reconcile(auth_client, lock_timeout_ms=100)
            assert busy.failed == 0
            assert await _status(db_engine, payment.id) == ("pending", None)

    await _reconcile(auth_client)
    assert await _status(db_engine, payment.id) == ("paid", None)


async def test_closing_a_lost_request_waits_for_a_busy_order(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    _, ready = await _order_ready(catalog, buyer)
    order_id = await _placed(ready)
    async with AsyncSession(db_engine) as session, session.begin():
        order = await session.get(Order, order_id)
        assert order is not None
        lost = Payment(
            order_id=order_id, gateway="fake", idempotency_key="k", amount=order.grand_total
        )
        session.add(lost)
        await session.flush()
        payment_id = lost.id

    async with AsyncSession(db_engine) as holder, holder.begin():
        await holder.execute(order_advisory_lock(order_id))
        await _reconcile(auth_client)
        assert await _status(db_engine, payment_id) == ("pending", None)

    await _reconcile(auth_client)
    assert await _status(db_engine, payment_id) == ("failed", "request_lost")


class _CountingDown(_Down):
    def __init__(self) -> None:
        self.calls = 0

    async def verify(self, *, reference: str, amount: int) -> VerifyResult:
        self.calls += 1
        return await super().verify(reference=reference, amount=amount)


async def test_a_round_stops_after_three_unreachable_verifies(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer
) -> None:
    payments = await _three_paid_orders(auth_client, catalog, buyer)
    payments += await _three_paid_orders(auth_client, catalog, buyer)
    down = _CountingDown()

    result = await _reconcile(auth_client, down)

    assert down.calls == 3 and result.failed == 3  # the other three wait for a later round
