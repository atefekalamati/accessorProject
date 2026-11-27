"""Staff cancel of a paid, unshipped order (ORD-11, PRD «مدیریت سفارش» ✓, ADR-063 R2)."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import pytest
from conftest import Account, Catalog, MakeAccount
from httpx import AsyncClient, Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from test_admin_refunds import _another_paid_attempt
from test_admin_shipment import _ship
from test_orders_cancel import _cancel, _placed
from test_orders_create import (
    API,
    Buyer,
    MakeBuyer,
    _error,
    _orders_go_first,
    buyer,
    codes,
    methods,
    shopper,
)
from test_payments_callback import _callback, _complete, _order_ready, _started

from app.db.models import (
    AuditLog,
    DiscountRedemption,
    InventoryItem,
    InventoryMovement,
    Order,
    OrderStatusHistory,
    Payment,
    ProductVariant,
)
from app.db.models.inventory import DEFAULT_WAREHOUSE_ID
from app.modules.orders.state import OrderState, check_transition
from app.shared.inventory import MAX_STOCK_QUANTITY

pytestmark = pytest.mark.integration

__all__ = ["_orders_go_first", "buyer", "codes", "methods", "shopper"]  # shared fixtures

ADMIN_ORDERS = f"{API}/admin/orders"


class Paid:
    def __init__(self, ready: Buyer, order_id: UUID, variant: ProductVariant, payment: Payment):
        self.ready, self.order_id, self.variant, self.payment = ready, order_id, variant, payment


async def _paid(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    quantity: int = 2,
    code: str | None = None,
) -> Paid:
    variant, ready = await _order_ready(catalog, buyer, quantity)
    if code is not None:
        applied = await auth_client.post(
            f"{API}/cart/discount", json={"code": code}, headers=ready.account.headers
        )
        assert applied.status_code == 200, applied.text
    order_id = await _placed(ready)
    payment = await _started(ready, order_id)
    await _complete(auth_client, payment)
    settled = await _callback(auth_client, payment.gateway_reference)
    assert settled.json()["outcome"] == "success", settled.text
    return Paid(ready, order_id, variant, payment)


async def _staff_cancel(client: AsyncClient, staff: Account, order_id: UUID) -> Response:
    return await client.post(f"{ADMIN_ORDERS}/{order_id}/cancel", headers=staff.headers)


async def _stock(engine: AsyncEngine, variant_id: UUID) -> tuple[int, int]:
    async with AsyncSession(engine) as session:
        item = (
            await session.scalars(
                select(InventoryItem).where(
                    InventoryItem.variant_id == variant_id,
                    InventoryItem.warehouse_id == DEFAULT_WAREHOUSE_ID,
                )
            )
        ).one()
        return item.total_quantity, item.reserved_quantity


async def _returns(engine: AsyncEngine, order_id: UUID) -> list[InventoryMovement]:
    async with AsyncSession(engine) as session:
        return list(
            await session.scalars(
                select(InventoryMovement).where(
                    InventoryMovement.reference_type == "order",
                    InventoryMovement.reference_id == order_id,
                    InventoryMovement.movement_type == "return",
                )
            )
        )


async def _order(engine: AsyncEngine, order_id: UUID) -> Order:
    async with AsyncSession(engine) as session:
        found = await session.get(Order, order_id)
    assert found is not None
    return found


async def _payment(engine: AsyncEngine, payment_id: UUID) -> Payment:
    async with AsyncSession(engine) as session:
        found = await session.get(Payment, payment_id)
    assert found is not None
    return found


async def _audits(engine: AsyncEngine, entity_id: UUID, action: str) -> list[AuditLog]:
    async with AsyncSession(engine) as session:
        return list(
            await session.scalars(
                select(AuditLog).where(AuditLog.entity_id == entity_id, AuditLog.action == action)
            )
        )


# --- pure ------------------------------------------------------------------------------


def test_state_rules_for_a_paid_cancel() -> None:
    def why(status: str, payment: str, shipment: str, field: Any, target: str) -> str | None:
        return check_transition(OrderState(status, payment, shipment), field, target)

    from app.db.models import StatusField as F

    assert why("confirmed", "paid", "not_shipped", F.ORDER, "cancelled") is None
    assert why("confirmed", "paid", "preparing", F.ORDER, "cancelled") is None
    assert why("confirmed", "paid", "shipped", F.ORDER, "cancelled") == "already_shipped"
    assert why("confirmed", "paid", "delivered", F.ORDER, "cancelled") == "already_shipped"
    assert why("pending_payment", "paid", "not_shipped", F.ORDER, "cancelled") == "already_paid"
    assert why("cancelled", "paid", "not_shipped", F.PAYMENT, "refund_required") is None
    assert why("confirmed", "paid", "not_shipped", F.PAYMENT, "refund_required") == (
        "requires_order_cancelled"
    )
    # A cancelled order is never prepared, shipped or delivered.
    for shipment, target in (
        ("not_shipped", "preparing"),
        ("preparing", "shipped"),
        ("shipped", "delivered"),
    ):
        assert why("cancelled", "refund_required", shipment, F.SHIPMENT, target) == (
            "requires_order_confirmed"
        )


# --- the cancel ---------------------------------------------------------------------------


async def test_cancel_owes_the_money_and_returns_the_stock(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    catalog: Catalog,
    buyer: MakeBuyer,
    db_engine: AsyncEngine,
) -> None:
    paid = await _paid(auth_client, catalog, buyer, quantity=2)
    staff = await make_account("admin")
    before = await _stock(db_engine, paid.variant.id)
    paid_amount = (await _payment(db_engine, paid.payment.id)).paid_amount

    response = await _staff_cancel(auth_client, staff, paid.order_id)

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert (response.json()["status"], response.json()["payment_status"]) == (
        "cancelled",
        "refund_required",
    )
    order = await _order(db_engine, paid.order_id)
    assert (order.cancel_reason, order.shipment_status) == ("admin", "not_shipped")
    payment = await _payment(db_engine, paid.payment.id)
    assert (payment.status, payment.failure_reason, payment.paid_amount) == (
        "refund_required",
        "order_cancelled",
        paid_amount,
    )
    [movement] = await _returns(db_engine, paid.order_id)
    assert (movement.quantity, movement.created_by) == (2, staff.id)
    assert await _stock(db_engine, paid.variant.id) == (before[0] + 2, before[1])
    by_staff = [
        audit
        for audit in await _audits(db_engine, paid.order_id, "order.status_changed")
        if audit.actor_user_id == staff.id
    ]
    assert len(by_staff) == 2  # order → cancelled, payment → refund_required
    async with AsyncSession(db_engine) as session:
        history = [
            (row.field, row.new_status, row.actor_user_id)
            for row in await session.scalars(
                select(OrderStatusHistory)
                .where(OrderStatusHistory.order_id == paid.order_id)
                .order_by(OrderStatusHistory.created_at, OrderStatusHistory.id)
            )
        ][-2:]
    assert history == [
        ("order", "cancelled", staff.id),
        ("payment", "refund_required", staff.id),
    ]
    assert len(await _audits(db_engine, paid.payment.id, "payment.refund_required")) == 1

    # Idempotent: the same request again changes nothing.
    again = await _staff_cancel(auth_client, staff, paid.order_id)
    assert again.status_code == 200 and again.json() == response.json()
    assert len(await _returns(db_engine, paid.order_id)) == 1

    # Then the existing full manual refund (ADM-08) settles the order.
    refunded = await auth_client.post(
        f"{API}/admin/payments/{paid.payment.id}/refund",
        json={"refund_reference": f"BANK-{paid.order_id.hex[:10]}"},
        headers=staff.headers,
    )
    assert refunded.status_code == 200, refunded.text
    assert refunded.json()["refund_amount"] == paid_amount
    assert (await _order(db_engine, paid.order_id)).payment_status == "refunded"


async def test_preparing_is_cancellable_and_then_never_shipped(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    catalog: Catalog,
    buyer: MakeBuyer,
    db_engine: AsyncEngine,
) -> None:
    paid = await _paid(auth_client, catalog, buyer)
    staff = await make_account("admin")
    assert (await _ship(auth_client, staff, paid.order_id, "preparing")).status_code == 200

    assert (await _staff_cancel(auth_client, staff, paid.order_id)).status_code == 200

    shipped = await _ship(auth_client, staff, paid.order_id, "shipped", tracking_code="IR1")
    _error(shipped, 422, "INVALID_STATE_TRANSITION")
    assert (await _order(db_engine, paid.order_id)).shipment_status == "preparing"


async def test_a_shipped_order_is_not_cancelled(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    catalog: Catalog,
    buyer: MakeBuyer,
    db_engine: AsyncEngine,
) -> None:
    paid = await _paid(auth_client, catalog, buyer)
    staff = await make_account("admin")
    await _ship(auth_client, staff, paid.order_id, "preparing")
    await _ship(auth_client, staff, paid.order_id, "shipped", tracking_code="IR2")

    response = await _staff_cancel(auth_client, staff, paid.order_id)

    _error(response, 422, "INVALID_STATE_TRANSITION")
    assert response.json()["error"]["details"][0]["type"] == "already_shipped"
    order = await _order(db_engine, paid.order_id)
    assert (order.status, order.payment_status) == ("confirmed", "paid")
    assert await _returns(db_engine, paid.order_id) == []


async def test_a_delivered_order_is_not_cancelled(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    catalog: Catalog,
    buyer: MakeBuyer,
    db_engine: AsyncEngine,
) -> None:
    paid = await _paid(auth_client, catalog, buyer)
    staff = await make_account("admin")
    for status, body in (
        ("preparing", {}),
        ("shipped", {"tracking_code": "IR3"}),
        ("delivered", {}),
    ):
        assert (await _ship(auth_client, staff, paid.order_id, status, **body)).status_code == 200

    response = await _staff_cancel(auth_client, staff, paid.order_id)

    _error(response, 422, "INVALID_STATE_TRANSITION")
    assert (await _order(db_engine, paid.order_id)).payment_status == "paid"


async def test_the_discount_code_use_is_released(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    catalog: Catalog,
    buyer: MakeBuyer,
    codes: Any,
    db_engine: AsyncEngine,
) -> None:
    code = await codes(value=10_000)
    paid = await _paid(auth_client, catalog, buyer, code=code.code)
    staff = await make_account("admin")
    async with AsyncSession(db_engine) as session:
        assert (
            await session.scalar(
                select(DiscountRedemption.status).where(
                    DiscountRedemption.order_id == paid.order_id
                )
            )
            == "confirmed"
        )

    assert (await _staff_cancel(auth_client, staff, paid.order_id)).status_code == 200

    async with AsyncSession(db_engine) as session:
        assert (
            await session.scalar(
                select(DiscountRedemption.status).where(
                    DiscountRedemption.order_id == paid.order_id
                )
            )
            == "released"
        )
    [audit] = await _audits(db_engine, paid.order_id, "discount.redemption_released")
    assert audit.actor_user_id == staff.id
    assert audit.metadata_["diff"]["redemption"] == {
        "before": "confirmed",
        "after": "released",
        "changed": True,
    }


async def test_a_duplicate_payment_settles_after_both_refunds(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    catalog: Catalog,
    buyer: MakeBuyer,
    db_engine: AsyncEngine,
) -> None:
    paid = await _paid(auth_client, catalog, buyer)
    order = await _order(db_engine, paid.order_id)
    duplicate = await _another_paid_attempt(
        auth_client, db_engine, paid.order_id, order.grand_total
    )
    assert (await _payment(db_engine, duplicate)).status == "refund_required"
    staff = await make_account("admin")

    async def dashboard() -> int:
        response = await auth_client.get(f"{API}/admin/dashboard", headers=staff.headers)
        assert response.status_code == 200, response.text
        count: int = response.json()["refund_required_payments"]
        return count

    owed_before = await dashboard()
    assert (await _staff_cancel(auth_client, staff, paid.order_id)).status_code == 200
    assert await dashboard() == owed_before + 1  # the first payment joins the duplicate

    for index, payment_id in enumerate((paid.payment.id, duplicate)):
        refunded = await auth_client.post(
            f"{API}/admin/payments/{payment_id}/refund",
            json={"refund_reference": f"BANK-{index}-{paid.order_id.hex[:10]}"},
            headers=staff.headers,
        )
        assert refunded.status_code == 200, refunded.text
        expected = "refund_required" if index == 0 else "refunded"
        assert (await _order(db_engine, paid.order_id)).payment_status == expected


async def test_the_customer_still_cannot_cancel_a_paid_order(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    paid = await _paid(auth_client, catalog, buyer)

    response = await _cancel(paid.ready, paid.order_id)

    _error(response, 422, "INVALID_STATE_TRANSITION")
    assert response.json()["error"]["details"][0]["type"] == "not_allowed"  # as before ORD-11
    assert (await _order(db_engine, paid.order_id)).status == "confirmed"


async def test_stock_limit_writes_nothing(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    catalog: Catalog,
    buyer: MakeBuyer,
    db_engine: AsyncEngine,
) -> None:
    paid = await _paid(auth_client, catalog, buyer)
    staff = await make_account("admin")
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            update(InventoryItem)
            .where(InventoryItem.variant_id == paid.variant.id)
            .values(total_quantity=MAX_STOCK_QUANTITY)
        )

    response = await _staff_cancel(auth_client, staff, paid.order_id)

    _error(response, 422, "BUSINESS_RULE_VIOLATION")
    assert response.json()["error"]["details"][0]["type"] == "stock_limit"
    order = await _order(db_engine, paid.order_id)
    assert (order.status, order.payment_status) == ("confirmed", "paid")
    assert (await _payment(db_engine, paid.payment.id)).status == "paid"
    async with AsyncSession(db_engine) as session:
        history = await session.scalars(
            select(OrderStatusHistory).where(
                OrderStatusHistory.order_id == paid.order_id,
                OrderStatusHistory.new_status == "cancelled",
            )
        )
        assert list(history) == []


async def test_permissions(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    catalog: Catalog,
    buyer: MakeBuyer,
    db_engine: AsyncEngine,
) -> None:
    paid = await _paid(auth_client, catalog, buyer)
    url = f"{ADMIN_ORDERS}/{paid.order_id}/cancel"
    assert (await auth_client.post(url)).status_code == 401
    for role in ("support", "content_manager"):
        account = await make_account(role)
        _error(await auth_client.post(url, headers=account.headers), 403, "FORBIDDEN")
    _error(await auth_client.post(url, headers=paid.ready.account.headers), 403, "FORBIDDEN")
    assert (await _order(db_engine, paid.order_id)).status == "confirmed"


# --- concurrency -----------------------------------------------------------------------


async def test_concurrent_cancels_return_the_stock_once(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    catalog: Catalog,
    buyer: MakeBuyer,
    db_engine: AsyncEngine,
) -> None:
    paid = await _paid(auth_client, catalog, buyer, quantity=2)
    staff = await make_account("admin")
    before = await _stock(db_engine, paid.variant.id)

    responses = await asyncio.gather(
        *(_staff_cancel(auth_client, staff, paid.order_id) for _ in range(3))
    )

    assert [r.status_code for r in responses] == [200, 200, 200]
    assert len(await _returns(db_engine, paid.order_id)) == 1
    assert await _stock(db_engine, paid.variant.id) == (before[0] + 2, before[1])
    assert len(await _audits(db_engine, paid.payment.id, "payment.refund_required")) == 1


async def test_cancel_racing_a_stock_adjustment_and_a_new_order(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    catalog: Catalog,
    buyer: MakeBuyer,
    db_engine: AsyncEngine,
) -> None:
    paid = await _paid(auth_client, catalog, buyer, quantity=2)
    staff = await make_account("admin")
    other = await buyer((paid.variant, 1))
    fingerprint = (await other.quote())["fingerprint"]
    before = await _stock(db_engine, paid.variant.id)

    cancelled, adjusted, placed = await asyncio.wait_for(
        asyncio.gather(
            _staff_cancel(auth_client, staff, paid.order_id),
            auth_client.patch(
                f"{API}/admin/inventory/{paid.variant.id}",
                json={"adjustment_type": "increase", "quantity": 1, "reason": "count"},
                headers=staff.headers,
            ),
            other.order(fingerprint=fingerprint),
        ),
        timeout=30,
    )

    assert (cancelled.status_code, adjusted.status_code, placed.status_code) == (200, 200, 201), (
        cancelled.text,
        adjusted.text,
        placed.text,
    )
    assert await _stock(db_engine, paid.variant.id) == (before[0] + 3, before[1] + 1)
