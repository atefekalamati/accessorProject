"""Order status transitions: tables, guards, history, audit, concurrency (ORD-05)."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import pytest
from conftest import MakeAccount, MakeOrder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from test_reservation_jobs import _wait_for_lock_waiter

from app.core.errors import AppError
from app.db.models import (
    AuditLog,
    CancelReason,
    Order,
    OrderStatus,
    OrderStatusHistory,
    PaymentStatus,
    ShipmentStatus,
    StatusField,
)
from app.modules.orders.state import TRANSITIONS, VALUES, OrderState, check_transition
from app.modules.orders.state_service import OrderStateService

OS, PS, SS = OrderStatus, PaymentStatus, ShipmentStatus

# --- pure ----------------------------------------------------------------------------


def _permissive(field: StatusField, current: str, target: str) -> OrderState:
    """``current`` on ``field`` and the other fields set so no cross-field guard blocks."""
    if field is StatusField.ORDER:
        payment = PS.UNPAID if target == OS.CANCELLED else PS.PAID
        shipment = SS.DELIVERED if target == OS.COMPLETED else SS.NOT_SHIPPED
        return OrderState(current, payment, shipment)
    if field is StatusField.PAYMENT:
        order = OS.CANCELLED if target == PS.REFUND_REQUIRED else OS.PENDING_PAYMENT
        return OrderState(order, current, SS.NOT_SHIPPED)
    return OrderState(OS.CONFIRMED, PS.PAID, current)


@pytest.mark.parametrize("field", list(StatusField))
def test_every_pair_follows_the_table(field: StatusField) -> None:
    for current in sorted(VALUES[field]):
        for target in sorted(VALUES[field]):
            allowed = target in TRANSITIONS[field].get(current, frozenset())
            why = check_transition(_permissive(field, current, target), field, target)
            assert (why is None) == allowed, (field, current, target, why)


@pytest.mark.parametrize(
    ("state", "field", "target", "why"),
    [
        (
            OrderState(OS.PENDING_PAYMENT, PS.PENDING, SS.NOT_SHIPPED),
            StatusField.ORDER,
            OS.CONFIRMED,
            "requires_payment_paid",
        ),
        (
            OrderState(OS.CONFIRMED, PS.PAID, SS.SHIPPED),
            StatusField.ORDER,
            OS.COMPLETED,
            "requires_shipment_delivered",
        ),
        (
            OrderState(OS.PENDING_PAYMENT, PS.PAID, SS.NOT_SHIPPED),
            StatusField.ORDER,
            OS.CANCELLED,
            "already_paid",
        ),
        (
            OrderState(OS.CANCELLED, PS.UNPAID, SS.NOT_SHIPPED),
            StatusField.PAYMENT,
            PS.PENDING,
            "requires_order_pending_payment",
        ),
        (
            OrderState(OS.CANCELLED, PS.FAILED, SS.NOT_SHIPPED),
            StatusField.PAYMENT,
            PS.PAID,
            "requires_order_pending_payment",
        ),
        (
            OrderState(OS.PENDING_PAYMENT, PS.PENDING, SS.NOT_SHIPPED),
            StatusField.PAYMENT,
            PS.REFUND_REQUIRED,
            "requires_order_cancelled",
        ),
        (
            OrderState(OS.PENDING_PAYMENT, PS.UNPAID, SS.NOT_SHIPPED),
            StatusField.SHIPMENT,
            SS.PREPARING,
            "requires_order_confirmed",
        ),
        (
            OrderState(OS.PENDING_PAYMENT, PS.UNPAID, SS.NOT_SHIPPED),
            StatusField.ORDER,
            OS.PENDING_PAYMENT,
            "same_status",
        ),
        (
            OrderState(OS.PENDING_PAYMENT, PS.UNPAID, SS.NOT_SHIPPED),
            StatusField.ORDER,
            "shipped",
            "unknown_status",
        ),
    ],
)
def test_guards(state: OrderState, field: StatusField, target: str, why: str) -> None:
    assert check_transition(state, field, target) == why


# --- service (integration) -----------------------------------------------------------


async def _move(
    engine: AsyncEngine, order_id: UUID, field: StatusField, new: str, **kw: Any
) -> Order:
    async with AsyncSession(engine, expire_on_commit=False) as session, session.begin():
        moved = await OrderStateService(session).transition(
            order_id, field, new, actor_user_id=kw.pop("actor_user_id", None), **kw
        )
        assert moved.new_status == new and moved.old_status != new
        return moved.order


async def _audits(engine: AsyncEngine, order_id: UUID) -> list[AuditLog]:
    async with AsyncSession(engine) as session:
        return list(
            await session.scalars(
                select(AuditLog)
                .where(AuditLog.entity_id == order_id, AuditLog.action == "order.status_changed")
                .order_by(AuditLog.created_at, AuditLog.id)
            )
        )


async def _history(engine: AsyncEngine, order_id: UUID) -> list[tuple[str, str | None, str]]:
    async with AsyncSession(engine) as session:
        rows = await session.scalars(
            select(OrderStatusHistory)
            .where(OrderStatusHistory.order_id == order_id)
            .order_by(OrderStatusHistory.created_at, OrderStatusHistory.id)
        )
        return [(row.field, row.old_status, row.new_status) for row in rows]


@pytest.mark.integration
async def test_the_happy_path_logs_history_and_audit(
    make_order: MakeOrder, db_engine: AsyncEngine
) -> None:
    order_id = await make_order()
    steps = [
        (StatusField.PAYMENT, PS.PENDING),
        (StatusField.PAYMENT, PS.PAID),
        (StatusField.ORDER, OS.CONFIRMED),
        (StatusField.SHIPMENT, SS.PREPARING),
        (StatusField.SHIPMENT, SS.SHIPPED),
        (StatusField.SHIPMENT, SS.DELIVERED),
        (StatusField.ORDER, OS.COMPLETED),
    ]
    for field, new in steps:
        await _move(db_engine, order_id, field, new, reason="ok")

    async with AsyncSession(db_engine) as session:
        order = await session.get(Order, order_id)
        audits = list(
            await session.scalars(
                select(AuditLog)
                .where(AuditLog.entity_id == order_id, AuditLog.action == "order.status_changed")
                .order_by(AuditLog.created_at, AuditLog.id)
            )
        )
    assert order is not None
    assert (order.status, order.payment_status, order.shipment_status) == (
        "completed",
        "paid",
        "delivered",
    )
    history = await _history(db_engine, order_id)
    assert [(field, new) for field, _, new in history] == [(f.value, n.value) for f, n in steps]
    assert history[0][1] == "unpaid"
    assert len(audits) == len(steps)
    assert audits[0].actor_user_id is None
    assert audits[0].metadata_["diff"]["payment_status"] == {
        "before": "unpaid",
        "after": "pending",
        "changed": True,
    }


@pytest.mark.integration
async def test_cancel_needs_a_reason_and_frees_refund_required(
    make_order: MakeOrder, db_engine: AsyncEngine
) -> None:
    order_id = await make_order()
    with pytest.raises(ValueError):
        await _move(db_engine, order_id, StatusField.ORDER, OS.CANCELLED)
    with pytest.raises(ValueError):
        await _move(
            db_engine, order_id, StatusField.PAYMENT, PS.PENDING, cancel_reason=CancelReason.ADMIN
        )
    await _move(db_engine, order_id, StatusField.PAYMENT, PS.PENDING)
    cancelled = await _move(
        db_engine, order_id, StatusField.ORDER, OS.CANCELLED, cancel_reason=CancelReason.EXPIRED
    )
    # A late success after the cancel: refund by hand (D32).
    refunded = await _move(db_engine, order_id, StatusField.PAYMENT, PS.REFUND_REQUIRED)
    assert (cancelled.status, cancelled.cancel_reason) == ("cancelled", "expired")
    assert refunded.payment_status == "refund_required"


@pytest.mark.integration
async def test_invalid_moves_are_422_and_unknown_orders_404(
    make_order: MakeOrder, db_engine: AsyncEngine
) -> None:
    order_id = await make_order()
    for field, new, why in (
        (StatusField.ORDER, OS.CONFIRMED, "requires_payment_paid"),
        (StatusField.ORDER, OS.PENDING_PAYMENT, "same_status"),
        (StatusField.SHIPMENT, SS.SHIPPED, "not_allowed"),
        (StatusField.PAYMENT, PS.PAID, "not_allowed"),
    ):
        with pytest.raises(AppError) as caught:
            await _move(db_engine, order_id, field, new)
        assert (caught.value.status_code, caught.value.code) == (422, "INVALID_STATE_TRANSITION")
        assert caught.value.details[0] == {
            "field": field.value,
            "from": {"order": "pending_payment", "payment": "unpaid", "shipment": "not_shipped"}[
                field.value
            ],
            "to": new,
            "type": why,
        }
    with pytest.raises(AppError) as missing:
        await _move(db_engine, uuid4(), StatusField.PAYMENT, PS.PENDING)
    assert missing.value.status_code == 404
    assert await _history(db_engine, order_id) == []
    assert await _audits(db_engine, order_id) == []


@pytest.mark.integration
async def test_concurrent_cancels_apply_once(make_order: MakeOrder, db_engine: AsyncEngine) -> None:
    order_id = await make_order()

    async def cancel() -> str:
        try:
            await _move(
                db_engine,
                order_id,
                StatusField.ORDER,
                OS.CANCELLED,
                cancel_reason=CancelReason.CUSTOMER,
            )
        except AppError as error:
            return str(error.code)
        return "ok"

    # A holds the row lock with its cancel uncommitted; B must queue behind it and then
    # see the cancelled order.
    async with AsyncSession(db_engine) as first, first.begin():
        await OrderStateService(first).transition(
            order_id,
            StatusField.ORDER,
            OS.CANCELLED,
            actor_user_id=None,
            cancel_reason=CancelReason.CUSTOMER,
        )
        second = asyncio.create_task(cancel())
        await _wait_for_lock_waiter(db_engine)
        assert not second.done()
    assert await second == "INVALID_STATE_TRANSITION"
    assert await _history(db_engine, order_id) == [("order", "pending_payment", "cancelled")]
    assert len(await _audits(db_engine, order_id)) == 1


@pytest.mark.integration
async def test_service_needs_the_callers_transaction(
    make_order: MakeOrder, db_engine: AsyncEngine
) -> None:
    order_id = await make_order()
    async with AsyncSession(db_engine) as session:
        with pytest.raises(RuntimeError):
            await OrderStateService(session).transition(
                order_id, StatusField.PAYMENT, PS.PENDING, actor_user_id=None
            )
    with pytest.raises(ValueError):
        await _move(db_engine, order_id, StatusField.PAYMENT, PS.PENDING, reason="x" * 501)


@pytest.mark.integration
async def test_a_user_actor_is_recorded(
    make_account: MakeAccount, make_order: MakeOrder, db_engine: AsyncEngine
) -> None:
    admin = await make_account("admin")
    order_id = await make_order()
    await _move(
        db_engine, order_id, StatusField.PAYMENT, PS.PENDING, actor_user_id=admin.id, reason=" x "
    )
    [audit] = await _audits(db_engine, order_id)
    assert audit.actor_user_id == admin.id
    async with AsyncSession(db_engine) as session:
        [row] = await session.scalars(
            select(OrderStatusHistory).where(OrderStatusHistory.order_id == order_id)
        )
    assert (row.actor_user_id, row.reason) == (admin.id, "x")
    with pytest.raises(ValueError):
        await _move(db_engine, order_id, StatusField.PAYMENT, PS.PAID, reason="   ")
