"""Payment abuse paths and races (PAY-05, ADR-049): callbacks racing the expiry sweep, a
customer cancel, a new order and init; callbacks after a cancel or a refund; init's
finish racing reconciliation's request_lost. Double, forged and wrong-amount callbacks
are in tests/test_payments_callback.py; reconciliation races in test_payment_reconcile.py.

Orderings that matter are forced with the order's advisory lock: a holder takes it, the
racers queue on it in a known order (PostgreSQL grants waiters first come, first served),
then the holder lets go.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import Any
from uuid import UUID, uuid4

import pytest
from conftest import Catalog
from httpx import AsyncClient
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from test_orders_cancel import _cancel, _expire_now, _placed, _redemption_status, _reservation
from test_orders_create import (
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
from test_payment_reconcile import LATER, _reconcile
from test_payments_callback import _callback, _complete, _item, _order_ready, _started
from test_payments_init import _app, _fake, _init, _order, _payments

from app.core.time import utc_now
from app.db.models import AuditLog, Order, Payment, ProductVariant
from app.modules.inventory.jobs import sweep_expired_reservations
from app.modules.orders.cancel import order_advisory_lock
from app.modules.payments.gateways.base import GatewayRequest
from app.modules.payments.gateways.fake import FakeGateway

pytestmark = pytest.mark.integration

__all__ = ["_orders_go_first", "buyer", "codes", "methods", "shopper"]  # shared fixtures


async def _waiters(engine: AsyncEngine, count: int) -> None:
    """Until ``count`` backends of this database wait on a lock (bounded polling)."""
    for _ in range(500):
        # A new transaction per poll: pg_stat_activity is cached per transaction.
        async with AsyncSession(engine) as session:
            waiting = await session.scalar(
                select(func.count())
                .select_from(text("pg_locks"))
                .where(
                    text(
                        "NOT granted AND pid IN (SELECT pid FROM pg_stat_activity"
                        " WHERE datname = current_database())"
                    )
                )
            )
        if int(waiting or 0) >= count:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"fewer than {count} transactions waited for a lock")


async def _in_order[T](engine: AsyncEngine, order_id: UUID, *calls: Awaitable[T]) -> list[T]:
    """Run ``calls`` so they take the order's advisory lock in the given order."""
    async with AsyncSession(engine) as holder, holder.begin():
        await holder.execute(order_advisory_lock(order_id))
        tasks = []
        for queued, call in enumerate(calls, start=1):
            tasks.append(asyncio.ensure_future(call))
            await _waiters(engine, queued)
    return list(await asyncio.gather(*tasks))


async def _paid_at_gateway(
    client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, codes: Any
) -> tuple[ProductVariant, Any, UUID, Payment]:
    variant, ready = await _order_ready(catalog, buyer)
    order_id = await _placed(ready, await _with_code(client, ready, await codes(value=1_000)))
    payment = await _started(ready, order_id)
    await _complete(client, payment)
    return variant, ready, order_id, payment


async def _sold(engine: AsyncEngine, variant: ProductVariant, order_id: UUID) -> None:
    order = await _order(engine, order_id)
    [payment] = await _payments(engine, order_id)
    item = await _item(engine, variant)
    assert payment.status == "paid"
    assert (order.status, order.payment_status) == ("confirmed", "paid")
    assert (await _reservation(engine, order_id)).status == "committed"
    assert (item.total_quantity, item.reserved_quantity) == (4, 0)
    assert await _redemption_status(engine, order_id) == "confirmed"


async def _refunded(
    engine: AsyncEngine,
    variant: ProductVariant,
    order_id: UUID,
    *,
    reason: str = "reservation_expired",
    reservation: str = "expired",
) -> None:
    """Money taken back by hand; the order cancelled and nothing consumed (D32)."""
    order = await _order(engine, order_id)
    [payment] = await _payments(engine, order_id)
    item = await _item(engine, variant)
    assert (payment.status, payment.failure_reason) == ("refund_required", reason)
    assert (order.status, order.payment_status) == ("cancelled", "refund_required")
    assert (await _reservation(engine, order_id)).status == reservation
    assert (item.total_quantity, item.reserved_quantity) == (5, 0)
    assert await _redemption_status(engine, order_id) == "released"


# --- success against the expiry sweep ------------------------------------------------


async def test_a_success_racing_the_expiry_sweep_never_sells(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, codes: Any, db_engine: AsyncEngine
) -> None:
    """Unforced race: no deadlock, nothing fails, and an expired reservation is never sold."""
    variant, _, order_id, payment = await _paid_at_gateway(auth_client, catalog, buyer, codes)
    await _expire_now(db_engine, order_id)

    callback, swept = await asyncio.gather(
        _callback(auth_client, payment.gateway_reference), sweep_expired_reservations(db_engine)
    )
    await sweep_expired_reservations(db_engine)  # whatever a busy lock skipped

    assert callback.status_code == 200, callback.text
    assert swept.failed == 0
    await _refunded(db_engine, variant, order_id)


async def test_a_callback_first_commits_expired_itself(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, codes: Any, db_engine: AsyncEngine
) -> None:
    variant, _, order_id, payment = await _paid_at_gateway(auth_client, catalog, buyer, codes)
    await _expire_now(db_engine, order_id)

    async with AsyncSession(db_engine) as holder, holder.begin():
        await holder.execute(order_advisory_lock(order_id))
        callback = asyncio.ensure_future(_callback(auth_client, payment.gateway_reference))
        await _waiters(db_engine, 1)
        # The sweep only try-locks the order: it skips it while the callback waits.
        skipped = await sweep_expired_reservations(db_engine)
    response = await callback

    assert skipped.skipped >= 1
    assert response.json()["outcome"] == "failed"
    await _refunded(db_engine, variant, order_id)


async def test_a_success_racing_a_live_reservation_sweep_is_sold(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, codes: Any, db_engine: AsyncEngine
) -> None:
    variant, _, order_id, payment = await _paid_at_gateway(auth_client, catalog, buyer, codes)

    callback, swept = await asyncio.gather(
        _callback(auth_client, payment.gateway_reference), sweep_expired_reservations(db_engine)
    )

    assert callback.json()["outcome"] == "success" and swept.failed == 0
    await _sold(db_engine, variant, order_id)


# --- success against a customer cancel -----------------------------------------------


@pytest.mark.parametrize("first", ["callback", "cancel"])
async def test_a_late_success_against_a_customer_cancel(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    codes: Any,
    db_engine: AsyncEngine,
    first: str,
) -> None:
    variant, ready, order_id, payment = await _paid_at_gateway(auth_client, catalog, buyer, codes)
    # The shop closed the attempt (a lost answer), so the customer may cancel; the gateway
    # did take the money.
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            update(Payment)
            .where(Payment.id == payment.id)
            .values(status="failed", failure_reason="superseded")
        )
        await session.execute(
            update(Order).where(Order.id == order_id).values(payment_status="failed")
        )
    # The callback verifies before it locks: let it reach the lock first when it leads.
    if first == "callback":
        callback, cancelled = await _in_order(
            db_engine,
            order_id,
            _callback(auth_client, payment.gateway_reference),
            _cancel(ready, order_id),
        )
        assert callback.json()["outcome"] == "success"
        _error(cancelled, 422, "INVALID_STATE_TRANSITION")
        await _sold(db_engine, variant, order_id)
    else:
        cancelled, callback = await _in_order(
            db_engine,
            order_id,
            _cancel(ready, order_id),
            _callback(auth_client, payment.gateway_reference),
        )
        assert cancelled.status_code == 200, cancelled.text
        assert callback.json()["outcome"] == "failed"
        await _refunded(
            db_engine, variant, order_id, reason="order_cancelled", reservation="released"
        )


async def test_a_cancel_while_the_customer_is_at_the_gateway_is_refused(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, codes: Any, db_engine: AsyncEngine
) -> None:
    variant, ready, order_id, payment = await _paid_at_gateway(auth_client, catalog, buyer, codes)

    cancelled, callback = await asyncio.gather(
        _cancel(ready, order_id), _callback(auth_client, payment.gateway_reference)
    )

    # Pending payment: 409; once paid: 422. Either way the sale stands.
    assert cancelled.json()["error"]["code"] in ("PAYMENT_IN_PROGRESS", "INVALID_STATE_TRANSITION")
    assert callback.json()["outcome"] == "success"
    await _sold(db_engine, variant, order_id)


# --- success against the same customer's other requests ------------------------------


async def test_a_success_racing_a_new_order_of_the_same_customer(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, codes: Any, db_engine: AsyncEngine
) -> None:
    variant, ready, order_id, payment = await _paid_at_gateway(auth_client, catalog, buyer, codes)

    # Both lock the customer's cart first: they serialize, never deadlock (ADR-048).
    callback, again = await asyncio.gather(
        _callback(auth_client, payment.gateway_reference),
        # No fresh quote: the cart may already be empty when this runs.
        ready.order(fingerprint="0" * 64),
    )

    assert callback.json()["outcome"] == "success"
    error = again.json()["error"]
    # Before the payment: the live pending order. After it: the ordered lines left the
    # cart, which is now empty (checked before the fingerprint).
    assert (again.status_code, error["code"]) in (
        (409, "ORDER_PENDING"),
        (422, "BUSINESS_RULE_VIOLATION"),
    ), again.text
    if again.status_code == 422:
        assert error["details"][0]["type"] == "cart_empty"
    await _sold(db_engine, variant, order_id)


async def test_init_racing_the_callback_resumes_or_refuses(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, codes: Any, db_engine: AsyncEngine
) -> None:
    variant, ready, order_id, payment = await _paid_at_gateway(auth_client, catalog, buyer, codes)

    started, callback = await asyncio.gather(
        _init(ready, order_id), _callback(auth_client, payment.gateway_reference)
    )

    assert callback.json()["outcome"] == "success"
    if started.status_code == 201:
        assert started.json()["payment_id"] == str(payment.id)  # resumed, not a second one
    else:
        _error(started, 422, "INVALID_STATE_TRANSITION", "order_not_payable")
    await _sold(db_engine, variant, order_id)


# --- callbacks after the fact --------------------------------------------------------


async def test_callbacks_after_the_order_was_cancelled_by_expiry_refund_once(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, codes: Any, db_engine: AsyncEngine
) -> None:
    variant, ready, order_id, payment = await _paid_at_gateway(auth_client, catalog, buyer, codes)
    await _expire_now(db_engine, order_id)
    _error(await _init(ready, order_id), 409, "RESERVATION_EXPIRED")  # cancels lazily

    first = await _callback(auth_client, payment.gateway_reference)
    replay = await _callback(auth_client, payment.gateway_reference)

    assert (first.json()["outcome"], replay.json()["outcome"]) == ("failed", "failed")
    # init's lazy cancel released the active reservation (it had already expired).
    await _refunded(db_engine, variant, order_id, reservation="released")
    refunds = await _count(
        db_engine,
        AuditLog,
        AuditLog.entity_id == payment.id,
        AuditLog.action == "payment.refund_required",
    )
    assert refunds == 1


async def test_a_paid_order_is_sold_even_if_its_product_was_deleted_since(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, codes: Any, db_engine: AsyncEngine
) -> None:
    variant, _, order_id, payment = await _paid_at_gateway(auth_client, catalog, buyer, codes)
    await catalog.set(ProductVariant, variant.id, deleted_at=utc_now())

    response = await _callback(auth_client, payment.gateway_reference)

    # The order holds its own snapshot and reservation; a later delete cannot undo a sale.
    assert response.json()["outcome"] == "success"
    await _sold(db_engine, variant, order_id)


# --- init's finish against reconciliation --------------------------------------------


class _SlowRequest(FakeGateway):
    """Reconciliation closes the payment as request_lost while the gateway answers."""

    def __init__(self, client: AsyncClient, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._client = client

    async def request(self, *, payment_id: UUID, amount: int, callback_url: str) -> GatewayRequest:
        answer = await super().request(
            payment_id=payment_id, amount=amount, callback_url=callback_url
        )
        await _reconcile(self._client)
        return answer


async def test_init_finishing_after_reconciliation_closed_the_request(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    _, ready = await _order_ready(catalog, buyer)
    order_id = await _placed(ready)
    app = _app(auth_client)
    fake = _fake(auth_client)
    key = str(uuid4())
    app.state.payment_gateway = _SlowRequest(
        auth_client, db_engine, base_url="http://x", session_seconds=900
    )
    try:
        _error(await _init(ready, order_id, key), 409, "PAYMENT_IN_PROGRESS", "request_superseded")
    finally:
        app.state.payment_gateway = fake

    [lost] = await _payments(db_engine, order_id)
    assert (lost.status, lost.failure_reason, lost.gateway_reference) == (
        "failed",
        "request_lost",
        None,
    )
    # Nothing was stored for the key: the same key starts afresh.
    retry = await _init(ready, order_id, key)
    assert retry.status_code == 201, retry.text


async def test_reconciliation_after_init_finished_leaves_the_payment(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    _, ready = await _order_ready(catalog, buyer)
    order_id = await _placed(ready)
    payment = await _started(ready, order_id)  # tx2 stored the reference

    await _reconcile(auth_client, now=utc_now() + LATER)

    [still] = await _payments(db_engine, order_id)
    assert (still.id, still.status) == (payment.id, "pending")  # verified: still at the gateway


async def test_payment_responses_are_never_cached(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, codes: Any
) -> None:
    _, ready, order_id, payment = await _paid_at_gateway(auth_client, catalog, buyer, codes)

    resumed = await _init(ready, order_id)
    settled = await _callback(auth_client, payment.gateway_reference)

    assert (resumed.status_code, settled.status_code) == (201, 200)
    assert resumed.headers["cache-control"] == settled.headers["cache-control"] == "no-store"
