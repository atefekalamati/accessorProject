"""Cancel an order and free what it holds (ORD-06, ADR-050).

Used by the customer cancel endpoint and by the reservation expiry job. Runs in the
caller's transaction and never commits.

Lock order (ADR-048): order advisory → order row ``FOR UPDATE`` → inventory items →
reservation row → redemption. The order row takes a full ``FOR UPDATE`` (not ``NO KEY
UPDATE``): ``OrderStateService.transition`` locks it again with ``FOR UPDATE``, and
upgrading a weaker lock after the inventory locks could wait on others' KEY SHARE.

The cancel reason is decided after the reservation's locks: a reservation that had
already expired (``released_at >= expires_at``, or closed as expired) cancels the order
as ``expired`` with the system as actor (lazy expiry, D34), even on a customer request.
Invariant: every path that closes an order's reservation without committing it also
cancels the order in the same transaction.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from fastapi import Request
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, ErrorCode
from app.db.models import (
    CancelReason,
    InventoryReservation,
    Order,
    OrderStatus,
    ReservationStatus,
    StatusField,
)
from app.modules.discounts.redemption import RedemptionService
from app.modules.discounts.redemption import ReleaseOutcome as RedemptionOutcome
from app.modules.inventory.reservation import (
    ORDER_LOCK_NAMESPACE,
    ReservationService,
    order_lock_key,
)
from app.modules.orders.state import check_transition
from app.modules.orders.state_service import OrderStateService, invalid_transition, state_of
from app.shared.audit import record_audit

logger = logging.getLogger(__name__)

CUSTOMER_REASON: Final = "cancelled by customer"
ADMIN_REASON: Final = "cancelled by staff"
EXPIRED_REASON: Final = "reservation expired"


@dataclass(frozen=True, slots=True)
class Cancellation:
    order: Order
    cancel_reason: CancelReason
    redemption: RedemptionOutcome


def order_advisory_lock(order_id: UUID, *, wait: bool = True) -> Select[tuple[Any]]:
    """The per-order advisory lock statement (blocking, or a try-lock for the job)."""
    lock = func.pg_advisory_xact_lock if wait else func.pg_try_advisory_xact_lock
    return select(lock(ORDER_LOCK_NAMESPACE, order_lock_key(order_id)))


async def lock_order(
    session: AsyncSession, order_id: UUID, *, user_id: UUID | None = None, skip_locked: bool = False
) -> Order | None:
    """The order row ``FOR UPDATE`` (optionally only the user's), fresh from the database."""
    statement = select(Order).where(Order.id == order_id)
    if user_id is not None:
        statement = statement.where(Order.user_id == user_id)
    statement = statement.with_for_update(skip_locked=skip_locked).execution_options(
        populate_existing=True
    )
    return (await session.scalars(statement)).one_or_none()


class OrderCancellation:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def check(self, order: Order) -> None:
        """422 ``INVALID_STATE_TRANSITION`` if the locked order cannot be cancelled."""
        why = check_transition(state_of(order), StatusField.ORDER, OrderStatus.CANCELLED)
        if why is not None:
            raise invalid_transition(StatusField.ORDER, order.status, OrderStatus.CANCELLED, why)

    async def cancel_locked(
        self,
        order: Order,
        *,
        actor_user_id: UUID | None,
        request: Request | None = None,
        force_expired: bool = False,
        requested_reason: CancelReason = CancelReason.CUSTOMER,
    ) -> Cancellation:
        """Cancel an order whose advisory lock and row the caller holds.

        ``actor_user_id=None`` is the system (expiry job); ``requested_reason`` says whether
        the customer or staff (``admin``, ADM-02) asked. ``force_expired`` cancels as an
        expiry whatever the reservation shows (the job's orphan pass). The state is checked
        before any side effect, so a refused cancel changes nothing.
        """
        if not self._session.in_transaction():
            raise RuntimeError("OrderCancellation needs the caller's transaction")
        self.check(order)
        if requested_reason not in (CancelReason.CUSTOMER, CancelReason.ADMIN):
            raise ValueError("requested_reason must be customer or admin; expiry is detected")
        reason_text = ADMIN_REASON if requested_reason is CancelReason.ADMIN else CUSTOMER_REASON
        expired = await self._free_stock(order.id, actor_user_id, reason_text) or force_expired
        # An expiry wins over who asked: the stock was already free (ADR-050).
        cancel_reason = CancelReason.EXPIRED if expired else requested_reason
        actor = None if expired else actor_user_id
        redemption = await RedemptionService(self._session).release(order.id)
        await OrderStateService(self._session).transition(
            order.id,
            StatusField.ORDER,
            OrderStatus.CANCELLED,
            actor_user_id=actor,
            reason=EXPIRED_REASON if expired else reason_text,
            cancel_reason=cancel_reason,
            request=request,
        )
        if redemption is RedemptionOutcome.RELEASED:
            # A code use stops counting: a sensitive change (CLAUDE.md §8), ids only.
            await record_audit(
                self._session,
                actor_id=actor,
                action="discount.redemption_released",
                entity_type="order",
                entity_id=order.id,
                # Only an unpaid order is cancelled, so its redemption was still pending.
                before={"redemption": "pending"},
                after={"redemption": "released", "cancel_reason": cancel_reason.value},
                request=request,
            )
        logger.info(
            "order.cancelled",
            extra={
                "order_id": str(order.id),
                "cancel_reason": cancel_reason.value,
                "redemption": redemption.value,
            },
        )
        return Cancellation(order, cancel_reason, redemption)

    async def _free_stock(self, order_id: UUID, actor_user_id: UUID | None, reason: str) -> bool:
        """Release the order's active reservation; True if it had already expired."""
        reservation = await self._latest_reservation(order_id)
        if reservation is None:
            return False
        if reservation.status == ReservationStatus.COMMITTED:
            # A pending_payment order never has one; refuse rather than guess (rolls back).
            raise ConflictError(
                code=ErrorCode.RESERVATION_ALREADY_CONSUMED,
                message="The order's reservation was already committed",
            )
        if reservation.status == ReservationStatus.ACTIVE:
            # ``release`` takes its own ``now`` after the item locks (no stale decision). An
            # already expired one is still released with the caller as actor (ADR-050); the
            # order is then cancelled as an expiry by the system.
            await ReservationService(self._session).release(
                reservation.id, reason=reason, actor_id=actor_user_id
            )
            await self._session.refresh(reservation)
        return _had_expired(reservation)

    async def _latest_reservation(self, order_id: UUID) -> InventoryReservation | None:
        statement = (
            select(InventoryReservation)
            .where(InventoryReservation.order_id == order_id)
            .order_by(InventoryReservation.created_at.desc(), InventoryReservation.id.desc())
            .limit(1)
        )
        return (await self._session.scalars(statement)).one_or_none()


def _had_expired(reservation: InventoryReservation) -> bool:
    if reservation.status == ReservationStatus.EXPIRED:
        return True
    released_at: datetime | None = reservation.released_at
    return released_at is not None and released_at >= reservation.expires_at
