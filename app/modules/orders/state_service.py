"""Apply one status transition to an order (ORD-05, ADR-047).

Runs in the caller's transaction and never commits. The order row is locked ``FOR UPDATE``
(lock order: idempotency → cart → order advisory → order row → inventory → code →
redemption), the move is checked against the fresh row, and every change writes one
``order_status_history`` row and one ``order.status_changed`` audit row.

Two moves in one transaction are two calls (e.g. D32: cancel the order, then
``refund_required``); the second re-lock of the same row is free. A system actor
(``actor_user_id=None``) names its source in ``reason`` (e.g. "reservation expired").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from uuid import UUID

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BusinessRuleError, ErrorCode, NotFoundError
from app.db.models import CancelReason, Order, OrderStatus, OrderStatusHistory, StatusField
from app.modules.orders.state import OrderState, check_transition
from app.shared.audit import record_audit

MAX_REASON_LENGTH: Final = 500
_COLUMNS: Final = {
    StatusField.ORDER: "status",
    StatusField.PAYMENT: "payment_status",
    StatusField.SHIPMENT: "shipment_status",
}


def _invalid(field: StatusField, current: str, new: str, why: str) -> BusinessRuleError:
    return BusinessRuleError(
        code=ErrorCode.INVALID_STATE_TRANSITION,
        message="This status change is not allowed",
        details=[{"field": field.value, "from": current, "to": new, "type": why}],
    )


@dataclass(frozen=True, slots=True)
class Transition:
    order: Order
    field: StatusField
    old_status: str
    new_status: str


def state_of(order: Order) -> OrderState:
    return OrderState(order.status, order.payment_status, order.shipment_status)


class OrderStateService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def transition(
        self,
        order_id: UUID,
        field: StatusField,
        new_status: str,
        *,
        actor_user_id: UUID | None,
        reason: str | None = None,
        cancel_reason: CancelReason | None = None,
        request: Request | None = None,
    ) -> Transition:
        """Move ``field`` to ``new_status``; 404 for an unknown order, 422 when invalid.

        ``actor_user_id=None`` is the system (jobs, payment callbacks). ``cancel_reason``
        is required for, and only for, cancelling the order.
        """
        if not self._session.in_transaction():
            raise RuntimeError("OrderStateService needs the caller's transaction")
        cancelling = field is StatusField.ORDER and new_status == OrderStatus.CANCELLED
        if cancelling != (cancel_reason is not None):
            raise ValueError("cancel_reason is required for, and only for, cancelling")
        if reason is not None:
            reason = reason.strip()
            if not 1 <= len(reason) <= MAX_REASON_LENGTH:
                raise ValueError(f"reason must be 1..{MAX_REASON_LENGTH} characters")

        order = (
            await self._session.scalars(
                select(Order)
                .where(Order.id == order_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).one_or_none()
        if order is None:
            raise NotFoundError(message="Order not found")
        current = state_of(order).of(field)
        why = check_transition(state_of(order), field, new_status)
        if why is not None:
            raise _invalid(field, current, new_status, why)

        setattr(order, _COLUMNS[field], str(new_status))
        if cancelling:
            order.cancel_reason = cancel_reason
        self._session.add(
            OrderStatusHistory(
                order_id=order.id,
                field=field,
                old_status=current,
                new_status=new_status,
                actor_user_id=actor_user_id,
                reason=reason,
            )
        )
        await self._session.flush()
        # The diff keeps changed keys only, so the column name tells which status moved.
        column = _COLUMNS[field]
        after: dict[str, str | None] = {column: new_status}
        if cancelling:
            after["cancel_reason"] = order.cancel_reason
        if reason is not None:
            after["reason"] = reason
        await record_audit(
            self._session,
            actor_id=actor_user_id,
            action="order.status_changed",
            entity_type="order",
            entity_id=order.id,
            before={column: current},
            after=after,
            request=request,
        )
        return Transition(order, field, current, str(new_status))
