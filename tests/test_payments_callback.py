"""POST /payments/callback and applying a verify result (PAY-03, ADR-049, ADR-051, D32)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID, uuid4

import pytest
from conftest import Catalog
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from test_checkout_validate import _add
from test_orders_cancel import (
    _expire_now,
    _placed,
    _redemption_status,
    _reservation,
)
from test_orders_create import (
    API,
    Buyer,
    MakeBuyer,
    _count,
    _error,
    _orders_go_first,
    _with_code,
    buyer,
    codes,
    methods,
    shopper,
)
from test_payments_init import _app, _fake, _init, _order, _payments

from app.db.models import (
    AuditLog,
    Cart,
    CartItem,
    InventoryItem,
    Payment,
    PaymentEvent,
    ProductVariant,
)
from app.modules.inventory.jobs import sweep_expired_reservations
from app.modules.payments.gateways.base import GatewayUnavailable, VerifyOutcome, VerifyResult
from app.modules.payments.processing import PaymentProcessor

pytestmark = pytest.mark.integration

__all__ = ["_orders_go_first", "buyer", "codes", "methods", "shopper"]  # shared fixtures

CALLBACK = f"{API}/payments/callback"


async def _started(ready: Buyer, order_id: UUID) -> Payment:
    response = await _init(ready, order_id)
    assert response.status_code == 201, response.text
    payments = await _payments_of(ready, order_id)
    return next(p for p in payments if str(p.id) == response.json()["payment_id"])


async def _payments_of(ready: Buyer, order_id: UUID) -> list[Payment]:
    engine = _app(ready.client).state.db_engine
    return await _payments(engine, order_id)


async def _complete(client: AsyncClient, payment: Payment, **body: Any) -> None:
    response = await client.post(
        f"{API}/payments/fake/{payment.gateway_reference}/complete",
        json={"result": "paid"} | body,
    )
    assert response.status_code == 200, response.text


def _fresh_ip() -> str:
    number = uuid4().int
    return f"10.{number % 250}.{(number >> 8) % 250}.{(number >> 16) % 250 + 1}"


async def _post(client: AsyncClient, ip: str | None = None, **kwargs: Any) -> Response:
    """POST to the callback from its own client IP (one per call by default), so the
    per-IP rate limit never couples tests; the rate-limit test pins one IP."""
    transport = ASGITransport(app=_app(client), client=(ip or _fresh_ip(), 50000))
    async with AsyncClient(transport=transport, base_url="http://testserver") as gateway:
        return await gateway.post(CALLBACK, **kwargs)


async def _callback(
    client: AsyncClient, reference: object, *, ip: str | None = None, **extra: Any
) -> Response:
    return await _post(client, ip, json={"reference": reference} | extra)


async def _item(engine: AsyncEngine, variant: ProductVariant) -> InventoryItem:
    async with AsyncSession(engine) as session:
        return (
            await session.scalars(
                select(InventoryItem).where(InventoryItem.variant_id == variant.id)
            )
        ).one()


async def _cart_of(engine: AsyncEngine, user_id: UUID) -> tuple[Cart, dict[UUID, int]]:
    async with AsyncSession(engine) as session:
        cart = (
            await session.scalars(
                select(Cart).where(Cart.user_id == user_id, Cart.status == "active")
            )
        ).one()
        lines = {
            line.variant_id: line.quantity
            for line in await session.scalars(select(CartItem).where(CartItem.cart_id == cart.id))
        }
    return cart, lines


async def _order_ready(catalog: Catalog, buyer: MakeBuyer, quantity: int = 1) -> Any:
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0), base_price=100_000)
    ready = await buyer((variant, quantity))
    return variant, ready


# --- success -------------------------------------------------------------------------


async def test_a_verified_payment_confirms_the_order(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, codes: Any, db_engine: AsyncEngine
) -> None:
    variant, ready = await _order_ready(catalog, buyer, quantity=2)
    order_id = await _placed(ready, await _with_code(auth_client, ready, await codes(value=1_000)))
    await _add(auth_client, ready.account, variant, 1)  # added after ordering: stays
    payment = await _started(ready, order_id)
    await _complete(auth_client, payment)

    response = await _callback(auth_client, payment.gateway_reference, status="paid")

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert (body["outcome"], body["order_status"], body["order_payment_status"]) == (
        "paid",
        "confirmed",
        "paid",
    )
    [paid] = await _payments(db_engine, order_id)
    assert (paid.status, paid.paid_amount, paid.failure_reason) == ("paid", paid.amount, None)
    assert paid.paid_at is not None and paid.raw_event is not None
    assert (await _reservation(db_engine, order_id)).status == "committed"
    item = await _item(db_engine, variant)
    assert (item.total_quantity, item.reserved_quantity) == (3, 0)
    assert await _redemption_status(db_engine, order_id) == "confirmed"
    cart, lines = await _cart_of(db_engine, ready.account.id)
    assert lines == {variant.id: 1}  # only the ordered quantity left the cart (D34)
    assert cart.discount_code_id is None  # the order used the code
    assert (
        await _count(
            db_engine, AuditLog, AuditLog.entity_id == paid.id, AuditLog.action == "payment.paid"
        )
        == 1
    )


async def test_repeated_and_concurrent_callbacks_apply_once(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    variant, ready = await _order_ready(catalog, buyer, quantity=2)
    order_id = await _placed(ready)
    payment = await _started(ready, order_id)
    await _complete(auth_client, payment)

    responses = await asyncio.gather(
        *(_callback(auth_client, payment.gateway_reference) for _ in range(3))
    )
    again = await _callback(auth_client, payment.gateway_reference)

    outcomes = sorted(response.json()["outcome"] for response in [*responses, again])
    assert outcomes == ["already_processed"] * 3 + ["paid"]
    assert all(response.status_code == 200 for response in [*responses, again])
    item = await _item(db_engine, variant)
    assert (item.total_quantity, item.reserved_quantity) == (3, 0)  # committed once
    assert (
        await _count(
            db_engine,
            AuditLog,
            AuditLog.entity_id == payment.id,
            AuditLog.action == "payment.paid",
        )
        == 1
    )


# --- failure, pending and forged callbacks ------------------------------------------


async def test_a_failed_payment_keeps_the_order_payable(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, codes: Any, db_engine: AsyncEngine
) -> None:
    _, ready = await _order_ready(catalog, buyer)
    order_id = await _placed(ready, await _with_code(auth_client, ready, await codes(value=1_000)))
    payment = await _started(ready, order_id)
    await _complete(auth_client, payment, result="failed")

    response = await _callback(auth_client, payment.gateway_reference)

    assert (response.status_code, response.json()["outcome"]) == (200, "failed")
    [failed] = await _payments(db_engine, order_id)
    assert (failed.status, failed.failure_reason) == ("failed", "declined")
    order = await _order(db_engine, order_id)
    assert (order.status, order.payment_status) == ("pending_payment", "failed")
    # The reservation and the code use stay for a retry (D34).
    assert (await _reservation(db_engine, order_id)).status == "active"
    assert await _redemption_status(db_engine, order_id) == "pending"
    assert (await _init(ready, order_id)).status_code == 201


async def test_the_callback_never_decides_only_verify_does(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    _, ready = await _order_ready(catalog, buyer)
    order_id = await _placed(ready)
    payment = await _started(ready, order_id)

    # A forged "paid" while the customer is still at the gateway changes nothing.
    forged = await _callback(auth_client, payment.gateway_reference, status="paid", amount=1)
    assert (forged.status_code, forged.json()["outcome"]) == (200, "pending")
    [still] = await _payments(db_engine, order_id)
    assert still.status == "pending"

    await _complete(auth_client, payment, result="failed")
    claimed = await _callback(auth_client, payment.gateway_reference, status="paid")
    assert claimed.json()["outcome"] == "failed"  # the gateway's answer wins


async def test_callback_errors_and_events(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    reference = f"FAKE-{uuid4().hex}"
    _error(await _callback(auth_client, reference, card="6037991234567890"), 404, "NOT_FOUND")
    _error(await _callback(auth_client, None), 400, "VALIDATION_ERROR")
    _error(await _post(auth_client, content=b"not json"), 400, "VALIDATION_ERROR")
    _error(await _post(auth_client, json=[1, 2]), 400, "VALIDATION_ERROR")
    _error(await _post(auth_client, json={"reference": "x" * 9000}), 400, "VALIDATION_ERROR")
    _error(await _callback(auth_client, 123), 400, "VALIDATION_ERROR")
    async with AsyncSession(db_engine) as session:
        event = (
            await session.scalars(
                select(PaymentEvent).where(PaymentEvent.gateway_reference == reference)
            )
        ).one()
    # Kept for support (unknown references too), redacted: no card number.
    assert (event.kind, event.payment_id, event.payload) == (
        "callback",
        None,
        {"reference": reference},
    )


async def test_callbacks_are_rate_limited_per_ip(auth_client: AsyncClient) -> None:
    app = _app(auth_client)
    saved = app.state.settings
    app.state.settings = saved.model_copy(update={"payment_callback_max_per_ip": 2})
    ip = _fresh_ip()
    try:
        responses = [await _callback(auth_client, f"FAKE-{uuid4().hex}", ip=ip) for _ in range(4)]
        other = await _callback(auth_client, f"FAKE-{uuid4().hex}")
    finally:
        app.state.settings = saved
    assert [response.status_code for response in responses] == [404, 404, 429, 429]
    assert responses[2].headers["retry-after"]
    assert other.status_code == 404  # another IP has its own window


# --- money taken that must go back ---------------------------------------------------


@pytest.mark.parametrize("amount_rial", ["different", "not_whole_toman"])
async def test_a_wrong_amount_is_refund_required_and_consumes_nothing(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    db_engine: AsyncEngine,
    caplog: pytest.LogCaptureFixture,
    amount_rial: str,
) -> None:
    variant, ready = await _order_ready(catalog, buyer)
    order_id = await _placed(ready)
    payment = await _started(ready, order_id)
    taken = payment.amount * 10 + (10 if amount_rial == "different" else 5)
    await _complete(auth_client, payment, amount_rial=taken)

    with caplog.at_level(logging.ERROR, logger="app.modules.payments.processing"):
        response = await _callback(auth_client, payment.gateway_reference)

    assert (response.status_code, response.json()["outcome"]) == (200, "amount_mismatch")
    [refund] = await _payments(db_engine, order_id)
    expected_paid = payment.amount + 1 if amount_rial == "different" else None
    assert (refund.status, refund.failure_reason, refund.paid_amount) == (
        "refund_required",
        "amount_mismatch",
        expected_paid,
    )
    assert any(record.levelno == logging.ERROR for record in caplog.records)
    order = await _order(db_engine, order_id)
    assert (order.status, order.payment_status) == ("pending_payment", "failed")
    assert (await _reservation(db_engine, order_id)).status == "active"  # not consumed
    assert (await _item(db_engine, variant)).total_quantity == 5
    assert (
        await _count(
            db_engine,
            AuditLog,
            AuditLog.entity_id == refund.id,
            AuditLog.action == "payment.amount_mismatch",
        )
        == 1
    )
    assert (await _init(ready, order_id)).status_code == 201  # the order stays payable


@pytest.mark.parametrize("swept", [True, False])
async def test_a_payment_after_the_reservation_expired_is_refund_required(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    codes: Any,
    db_engine: AsyncEngine,
    caplog: pytest.LogCaptureFixture,
    swept: bool,
) -> None:
    variant, ready = await _order_ready(catalog, buyer)
    order_id = await _placed(ready, await _with_code(auth_client, ready, await codes(value=1_000)))
    payment = await _started(ready, order_id)
    await _complete(auth_client, payment)
    await _expire_now(db_engine, order_id)
    if swept:
        await sweep_expired_reservations(db_engine)
        assert (await _order(db_engine, order_id)).status == "cancelled"

    with caplog.at_level(logging.WARNING, logger="app.modules.payments.processing"):
        response = await _callback(auth_client, payment.gateway_reference)

    assert (response.status_code, response.json()["outcome"]) == (200, "refund_required")
    [refund] = await _payments(db_engine, order_id)
    assert (refund.status, refund.failure_reason) == ("refund_required", "reservation_expired")
    order = await _order(db_engine, order_id)
    assert (order.status, order.cancel_reason, order.payment_status) == (
        "cancelled",
        "expired",
        "refund_required",
    )
    assert (await _reservation(db_engine, order_id)).status in ("expired", "released")
    assert (await _item(db_engine, variant)).total_quantity == 5  # never consumed (D32)
    assert await _redemption_status(db_engine, order_id) == "released"
    async with AsyncSession(db_engine) as session:
        audit = (
            await session.scalars(
                select(AuditLog).where(
                    AuditLog.entity_id == refund.id, AuditLog.action == "payment.refund_required"
                )
            )
        ).one()
    assert audit.actor_user_id is None
    warning = next(r for r in caplog.records if r.getMessage() == "payment.refund_required")
    assert warning.levelno == logging.WARNING
    fields = (warning.order_number, warning.payment_id, warning.amount)  # type: ignore[attr-defined]
    assert fields == (order.order_number, str(refund.id), refund.amount)


async def test_a_second_payment_on_a_paid_order_is_refund_required(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    variant, ready = await _order_ready(catalog, buyer)
    order_id = await _placed(ready)
    first = await _started(ready, order_id)
    await _complete(auth_client, first)
    assert (await _callback(auth_client, first.gateway_reference)).json()["outcome"] == "paid"
    # A second session for the same order (two tabs) that the customer also paid.
    fake = _fake(auth_client)
    second_id = uuid4()
    answer = await fake.request(payment_id=second_id, amount=first.amount, callback_url="x")
    async with AsyncSession(db_engine) as session, session.begin():
        session.add(
            Payment(
                id=second_id,
                order_id=order_id,
                gateway="fake",
                idempotency_key="second-tab",
                amount=first.amount,
                gateway_reference=answer.reference,
                redirect_url=answer.redirect_url,
                gateway_expires_at=answer.expires_at,
            )
        )
    assert await fake.complete(answer.reference, paid=True)

    response = await _callback(auth_client, answer.reference)

    assert response.json()["outcome"] == "duplicate_payment"
    async with AsyncSession(db_engine) as session:
        second = await session.get(Payment, second_id)
    assert second is not None
    assert (second.status, second.failure_reason) == ("refund_required", "duplicate_payment")
    order = await _order(db_engine, order_id)
    assert (order.status, order.payment_status) == ("confirmed", "paid")
    assert (await _item(db_engine, variant)).total_quantity == 4  # committed once


async def test_a_late_failure_after_another_payment_succeeded_changes_only_its_row(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    _, ready = await _order_ready(catalog, buyer)
    order_id = await _placed(ready)
    first = await _started(ready, order_id)
    await _complete(auth_client, first)
    await _callback(auth_client, first.gateway_reference)
    fake = _fake(auth_client)
    second_id = uuid4()
    answer = await fake.request(payment_id=second_id, amount=first.amount, callback_url="x")
    async with AsyncSession(db_engine) as session, session.begin():
        session.add(
            Payment(
                id=second_id,
                order_id=order_id,
                gateway="fake",
                idempotency_key="late",
                amount=first.amount,
                gateway_reference=answer.reference,
                redirect_url=answer.redirect_url,
                gateway_expires_at=answer.expires_at,
            )
        )
    await fake.complete(answer.reference, paid=False)

    response = await _callback(auth_client, answer.reference)

    assert response.json()["outcome"] == "failed"
    order = await _order(db_engine, order_id)
    assert (order.status, order.payment_status) == ("confirmed", "paid")  # paid → failed refused


async def test_raw_events_never_hold_card_numbers(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    _, ready = await _order_ready(catalog, buyer)
    order_id = await _placed(ready)
    payment = await _started(ready, order_id)
    await _complete(auth_client, payment)

    await _callback(auth_client, payment.gateway_reference, pan="6037-9912-3456-7890")

    async with AsyncSession(db_engine) as session:
        payloads: list[Any] = list(
            await session.scalars(
                select(PaymentEvent.payload).where(PaymentEvent.payment_id == payment.id)
            )
        )
        raw = await session.scalar(select(Payment.raw_event).where(Payment.id == payment.id))
    assert payloads and all("6037" not in str(payload) for payload in [*payloads, raw])


async def _other_payment(
    client: AsyncClient, engine: AsyncEngine, order_id: UUID, amount: int, **values: Any
) -> tuple[UUID, str]:
    """Another session for the same order (a second tab or a superseded attempt)."""
    fake = _fake(client)
    payment_id = uuid4()
    answer = await fake.request(payment_id=payment_id, amount=amount, callback_url="x")
    async with AsyncSession(engine) as session, session.begin():
        session.add(
            Payment(
                id=payment_id,
                order_id=order_id,
                gateway="fake",
                idempotency_key=f"other-{payment_id}",
                amount=amount,
                gateway_reference=answer.reference,
                redirect_url=answer.redirect_url,
                gateway_expires_at=answer.expires_at,
                **values,
            )
        )
    return payment_id, answer.reference


async def test_a_late_success_of_a_failed_attempt_is_applied(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    _, ready = await _order_ready(catalog, buyer)
    order_id = await _placed(ready)
    payment = await _started(ready, order_id)
    await _complete(auth_client, payment)
    # Closed as failed meanwhile (a lost answer), but the gateway did take the money.
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            sa_update(Payment)
            .where(Payment.id == payment.id)
            .values(status="failed", failure_reason="superseded")
        )

    response = await _callback(auth_client, payment.gateway_reference)

    assert response.json()["outcome"] == "paid"
    [paid] = await _payments(db_engine, order_id)
    assert (paid.status, paid.failure_reason) == ("paid", None)
    assert (await _order(db_engine, order_id)).status == "confirmed"
    # A FAILED verify after paid is ignored (the fake cannot fail a paid session).
    async with AsyncSession(db_engine) as session:
        applied = await PaymentProcessor(session).apply(
            payment.id, VerifyResult(VerifyOutcome.FAILED, failure_reason="declined")
        )
    assert (applied.outcome, applied.payment_status) == ("already_processed", "paid")


async def test_a_wrong_amount_on_an_old_attempt_leaves_the_live_one_alone(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    _, ready = await _order_ready(catalog, buyer)
    order_id = await _placed(ready)
    live = await _started(ready, order_id)
    old_id, old_ref = await _other_payment(
        auth_client, db_engine, order_id, live.amount, status="failed", failure_reason="superseded"
    )
    assert await _fake(auth_client).complete(old_ref, paid=True, amount_rial=10)

    response = await _callback(auth_client, old_ref)

    assert response.json()["outcome"] == "amount_mismatch"
    order = await _order(db_engine, order_id)
    # The live attempt is still at the gateway: the order stays pending (cancel stays 409).
    assert (order.status, order.payment_status) == ("pending_payment", "pending")
    async with AsyncSession(db_engine) as session:
        old = await session.get(Payment, old_id)
    assert old is not None and old.status == "refund_required"


async def test_a_wrong_amount_on_a_cancelled_order_is_refund_required(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    _, ready = await _order_ready(catalog, buyer)
    order_id = await _placed(ready)
    payment = await _started(ready, order_id)
    await _complete(auth_client, payment, amount_rial=10)
    await _expire_now(db_engine, order_id)
    await sweep_expired_reservations(db_engine)

    response = await _callback(auth_client, payment.gateway_reference)

    assert response.json()["outcome"] == "amount_mismatch"
    order = await _order(db_engine, order_id)
    assert (order.status, order.payment_status) == ("cancelled", "refund_required")


async def test_the_cart_loses_exactly_the_ordered_lines_and_keeps_another_code(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, codes: Any, db_engine: AsyncEngine
) -> None:
    _, ready = await _order_ready(catalog, buyer, quantity=2)
    order_id = await _placed(ready, await _with_code(auth_client, ready, await codes(value=1_000)))
    # After ordering, the customer applies another code to the cart.
    other = await codes(value=2_000)
    applied = await auth_client.post(
        f"{API}/cart/discount", json={"code": other.code}, headers=ready.account.headers
    )
    assert applied.status_code == 200, applied.text
    payment = await _started(ready, order_id)
    await _complete(auth_client, payment)

    assert (await _callback(auth_client, payment.gateway_reference)).json()["outcome"] == "paid"

    cart, lines = await _cart_of(db_engine, ready.account.id)
    assert lines == {}  # the line equalled the ordered quantity: removed
    assert cart.discount_code_id == other.id  # not the order's code: kept


class _Unreachable:
    """The fake gateway, except that verify never answers."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.name = inner.name

    async def verify(self, *, reference: str, amount: int) -> VerifyResult:
        raise GatewayUnavailable("timeout")

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


async def test_a_callback_when_verify_is_unreachable_is_503_and_kept(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    _, ready = await _order_ready(catalog, buyer)
    order_id = await _placed(ready)
    payment = await _started(ready, order_id)
    await _complete(auth_client, payment)
    app = _app(auth_client)
    fake = _fake(auth_client)
    app.state.payment_gateway = _Unreachable(fake)
    try:
        response = await _callback(auth_client, payment.gateway_reference)
    finally:
        app.state.payment_gateway = fake

    _error(response, 503, "PAYMENT_GATEWAY_UNAVAILABLE")
    [still] = await _payments(db_engine, order_id)
    assert still.status == "pending"  # the gateway's retry or reconciliation applies it
    stored = await _count(
        db_engine,
        PaymentEvent,
        PaymentEvent.payment_id == payment.id,
        PaymentEvent.kind == "callback",
    )
    assert stored == 1
    assert (await _callback(auth_client, payment.gateway_reference)).json()["outcome"] == "paid"
