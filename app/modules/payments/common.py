"""Shared steps of the payment paths (PAY-02..04, ADR-051).

Lock order (ADR-048 + payments): the order's user cart (only paths that change the cart)
→ order advisory → order row → payment row → inventory → reservation → redemption.
Never call a gateway while holding any of them.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now
from app.db.models import Order, Payment, PaymentEvent, PaymentStatus, StatusField
from app.modules.orders.cancel import lock_order, order_advisory_lock
from app.modules.orders.state import check_transition
from app.modules.orders.state_service import OrderStateService, state_of
from app.modules.payments.state import can_move
from app.shared.audit import record_audit

logger = logging.getLogger(__name__)


async def lock_order_row(
    session: AsyncSession, order_id: UUID, *, user_id: UUID | None = None
) -> Order | None:
    """Order advisory lock, then the order row ``FOR UPDATE`` (blocking)."""
    await session.execute(order_advisory_lock(order_id))
    return await lock_order(session, order_id, user_id=user_id)


async def lock_payment(session: AsyncSession, payment_id: UUID) -> Payment | None:
    statement = (
        select(Payment)
        .where(Payment.id == payment_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return (await session.scalars(statement)).one_or_none()


async def pending_payment_of(session: AsyncSession, order_id: UUID) -> Payment | None:
    """The order's pending payment, locked (the order row is already held)."""
    statement = (
        select(Payment)
        .where(Payment.order_id == order_id, Payment.status == PaymentStatus.PENDING)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return (await session.scalars(statement)).one_or_none()


async def move_payment(
    session: AsyncSession,
    payment: Payment,
    new_status: PaymentStatus,
    *,
    reason: str | None = None,
    now: datetime | None = None,
    paid_amount: int | None = None,
    raw: dict[str, Any] | None = None,
    request: Request | None = None,
) -> None:
    """Move a locked payment row; one ``payment.status_changed`` audit row (system actor).

    ``reason`` is required for failed and refund_required; paid and refund_required
    record when the gateway took the money (``paid_at``) and how much (``paid_amount``).
    """
    old = payment.status
    if not can_move(old, new_status):
        raise RuntimeError(f"payment {payment.id}: {old} → {new_status} is not allowed")
    closing = new_status in (PaymentStatus.FAILED, PaymentStatus.REFUND_REQUIRED)
    if closing != (reason is not None):
        raise ValueError("reason is required for, and only for, failed and refund_required")
    now = now or utc_now()
    payment.status = new_status
    payment.failure_reason = reason
    if new_status in (PaymentStatus.PAID, PaymentStatus.REFUND_REQUIRED):
        payment.paid_at = payment.paid_at or now
        payment.paid_amount = paid_amount
    if raw is not None:
        payment.raw_event = raw
        payment.verified_at = now
    await session.flush()
    after: dict[str, Any] = {"status": new_status.value}
    if reason is not None:
        after["reason"] = reason
    await record_audit(
        session,
        actor_id=None,
        action="payment.status_changed",
        entity_type="payment",
        entity_id=payment.id,
        before={"status": old},
        after=after,
        request=request,
    )


async def move_order_payment(
    session: AsyncSession,
    order: Order,
    new_status: PaymentStatus,
    *,
    actor_user_id: UUID | None,
    reason: str,
    request: Request | None = None,
) -> bool:
    """Move the order's ``payment_status`` when the order's state machine allows it.

    With several payments per order the order follows the latest decisive attempt; a
    move it does not allow (e.g. ``paid → failed`` for a second payment) changes only the
    payment row, so it is skipped here (False).
    """
    if check_transition(state_of(order), StatusField.PAYMENT, new_status) is not None:
        return False
    await OrderStateService(session).transition(
        order.id,
        StatusField.PAYMENT,
        new_status,
        actor_user_id=actor_user_id,
        reason=reason,
        request=request,
    )
    return True


async def close_payment(
    session: AsyncSession,
    payment: Payment,
    order: Order,
    reason: str,
    request: Request | None = None,
) -> None:
    """Close a locked pending payment as failed; the order may start a new one."""
    await move_payment(session, payment, PaymentStatus.FAILED, reason=reason)
    await move_order_payment(
        session,
        order,
        PaymentStatus.FAILED,
        actor_user_id=None,
        reason=f"payment {reason}",
        request=request,
    )


async def record_event(
    session: AsyncSession,
    *,
    gateway: str,
    kind: str,
    payload: dict[str, Any],
    reference: str | None = None,
    payment_id: UUID | None = None,
    ip: str | None = None,
) -> None:
    session.add(
        PaymentEvent(
            gateway=gateway,
            kind=kind,
            payload=payload,
            gateway_reference=reference,
            payment_id=payment_id,
            ip=ip,
        )
    )
    await session.flush()
