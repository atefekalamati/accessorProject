"""Apply a gateway's verify result to a payment (PAY-03, ADR-049, ADR-051, D31, D32, D34).

Shared by the callback, init's supersede and reconciliation (PAY-04). Only a verify
result decides anything; callback parameters never reach here. One transaction, in the
global lock order (ADR-048 + payments): the order's user cart → order advisory → order
row → payment row → inventory (commit) → reservation → redemption. The cart comes
first because a success removes the ordered quantities from it, and ORD-04 locks the
same cart before inventory.

Outcomes (each idempotent; a repeated result changes nothing):
- payment already ``paid``/``refund_required`` → ``already_processed``
- PENDING → nothing changes
- FAILED → the pending payment is ``failed``; the reservation and the code use stay for a
  retry within the reservation (D34)
- PAID with a wrong amount → ``refund_required`` (``amount_mismatch``); nothing consumed;
  the order stays payable (ADR-051)
- PAID on an order already paid → ``refund_required`` (``duplicate_payment``)
- PAID after the reservation expired or the order was cancelled → the order is cancelled
  (if not yet), payment ``refund_required`` (D32)
- PAID → reservation committed, code use confirmed, ordered quantities removed from the
  cart, payment ``paid``, order ``confirmed``
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum
from typing import Final
from uuid import UUID

from fastapi import Request
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now
from app.db.models import (
    CancelReason,
    Cart,
    CartItem,
    InventoryReservation,
    Order,
    OrderItem,
    OrderStatus,
    Payment,
    PaymentStatus,
    ReservationStatus,
    StatusField,
)
from app.db.models.payments import PaymentEventKind
from app.modules.cart.repository import CartRepository
from app.modules.discounts.redemption import ConfirmOutcome, RedemptionService
from app.modules.inventory.reservation import CommitOutcome, ReservationService
from app.modules.orders.cancel import OrderCancellation, lock_order, order_advisory_lock
from app.modules.orders.state_service import OrderStateService
from app.modules.payments.common import (
    lock_payment,
    move_order_payment,
    move_payment,
    record_event,
)
from app.modules.payments.gateways.base import VerifyOutcome, VerifyResult
from app.shared.audit import record_audit

logger = logging.getLogger(__name__)

AMOUNT_MISMATCH: Final = "amount_mismatch"
DUPLICATE_PAYMENT: Final = "duplicate_payment"
RESERVATION_EXPIRED: Final = "reservation_expired"
ORDER_CANCELLED: Final = "order_cancelled"


class Outcome(StrEnum):
    PAID = "paid"
    FAILED = "failed"
    PENDING = "pending"
    ALREADY_PROCESSED = "already_processed"
    AMOUNT_MISMATCH = "amount_mismatch"
    DUPLICATE = "duplicate_payment"
    REFUND_REQUIRED = "refund_required"
    # Reconciliation only: a lock was busy; try again next round.
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class Applied:
    outcome: Outcome
    order_number: str
    order_status: str
    order_payment_status: str
    payment_status: str


class BusyError(Exception):
    """Reconciliation found a lock taken (``try_locks``); nothing was changed."""


class PaymentProcessor:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def apply(
        self,
        payment_id: UUID,
        result: VerifyResult,
        *,
        request: Request | None = None,
        try_locks: bool = False,
        lock_timeout_ms: int | None = None,
    ) -> Applied:
        """Apply ``result`` in one transaction (opened here); see the module docstring.

        Reconciliation passes ``try_locks`` (a busy order is ``BusyError``) and a
        ``lock_timeout_ms`` (a busy cart or item fails fast with 55P03).
        """
        async with self._session.begin():
            if lock_timeout_ms is not None:
                await self._session.execute(
                    text(f"SET LOCAL lock_timeout = {int(lock_timeout_ms)}")
                )
            payment = await self._session.get(Payment, payment_id)
            if payment is None:
                raise LookupError(f"payment {payment_id} not found")
            user_id = await self._session.scalar(
                select(Order.user_id).where(Order.id == payment.order_id)
            )
            assert user_id is not None
            cart = await CartRepository(self._session).lock_user_cart(user_id)
            if try_locks:
                if not await self._session.scalar(
                    order_advisory_lock(payment.order_id, wait=False)
                ):
                    raise BusyError
                order = await lock_order(self._session, payment.order_id, skip_locked=True)
                if order is None:
                    raise BusyError
            else:
                await self._session.execute(order_advisory_lock(payment.order_id))
                order = await lock_order(self._session, payment.order_id)
                assert order is not None
            payment = await lock_payment(self._session, payment_id)
            assert payment is not None
            await record_event(
                self._session,
                gateway=payment.gateway,
                kind=PaymentEventKind.VERIFY,
                payload=result.raw,
                reference=payment.gateway_reference,
                payment_id=payment.id,
            )
            outcome = await self._decide(order, payment, cart.id, result, request)
            return Applied(
                outcome=outcome,
                order_number=order.order_number,
                order_status=order.status,
                order_payment_status=order.payment_status,
                payment_status=payment.status,
            )

    async def _decide(
        self,
        order: Order,
        payment: Payment,
        cart_id: UUID,
        result: VerifyResult,
        request: Request | None,
    ) -> Outcome:
        # Decided already: a late or repeated result never reopens a payment, and a
        # refunded one (ADM-08) stays refunded.
        if payment.status in (
            PaymentStatus.PAID,
            PaymentStatus.REFUND_REQUIRED,
            PaymentStatus.REFUNDED,
        ):
            return Outcome.ALREADY_PROCESSED
        if result.outcome is VerifyOutcome.PENDING:
            return Outcome.PENDING
        if result.outcome is VerifyOutcome.FAILED:
            if payment.status != PaymentStatus.PENDING:
                logger.info(
                    "payment.result_ignored",
                    extra={"payment_id": str(payment.id), "status": payment.status},
                )
                return Outcome.ALREADY_PROCESSED
            reason = result.failure_reason or "declined"
            await move_payment(
                self._session, payment, PaymentStatus.FAILED, reason=reason, raw=result.raw
            )
            await move_order_payment(
                self._session,
                order,
                PaymentStatus.FAILED,
                actor_user_id=None,
                reason=f"payment {reason}",
                request=request,
            )
            return Outcome.FAILED
        return await self._paid(order, payment, cart_id, result, request)

    async def _paid(
        self,
        order: Order,
        payment: Payment,
        cart_id: UUID,
        result: VerifyResult,
        request: Request | None,
    ) -> Outcome:
        if (
            result.amount is None
            or result.amount != payment.amount
            or (payment.amount != order.grand_total)
        ):
            # Only the order's live attempt moves the order: an old, closed attempt paid
            # late must not reopen a cancel while another payment is at the gateway.
            was_live = payment.status == PaymentStatus.PENDING
            await self._refund(
                order, payment, result, AMOUNT_MISMATCH, request, level=logging.ERROR
            )
            if order.status == OrderStatus.CANCELLED:
                order_status: PaymentStatus | None = PaymentStatus.REFUND_REQUIRED
            elif was_live and order.status == OrderStatus.PENDING_PAYMENT:
                order_status = PaymentStatus.FAILED
            else:
                order_status = None
            if order_status is not None:
                await move_order_payment(
                    self._session,
                    order,
                    order_status,
                    actor_user_id=None,
                    reason="payment amount mismatch",
                    request=request,
                )
            return Outcome.AMOUNT_MISMATCH
        if order.payment_status == PaymentStatus.PAID or order.status in (
            OrderStatus.CONFIRMED,
            OrderStatus.COMPLETED,
        ):
            await self._refund(order, payment, result, DUPLICATE_PAYMENT, request)
            return Outcome.DUPLICATE
        if order.status == OrderStatus.PENDING_PAYMENT:
            reservation_id = await self._reservation_of(order.id)
            committed = None
            if reservation_id is not None:
                # No ``now`` from here: commit takes it after its item locks, so a wait can
                # never let an expired reservation be consumed (D32).
                committed = await ReservationService(self._session).commit(reservation_id)
            if committed is not None and committed.outcome is CommitOutcome.ALREADY_COMMITTED:
                await self._refund(order, payment, result, DUPLICATE_PAYMENT, request)
                return Outcome.DUPLICATE
            if committed is None or committed.outcome is CommitOutcome.EXPIRED:
                # Paid after the reservation ended (D32): never consumed; the order goes.
                await OrderCancellation(self._session).cancel_locked(
                    order, actor_user_id=None, request=request, force_expired=True
                )
            else:
                await self._success(order, payment, cart_id, result, request)
                return Outcome.PAID
        reason = (
            RESERVATION_EXPIRED if order.cancel_reason == CancelReason.EXPIRED else ORDER_CANCELLED
        )
        await self._refund(order, payment, result, reason, request)
        await move_order_payment(
            self._session,
            order,
            PaymentStatus.REFUND_REQUIRED,
            actor_user_id=None,
            reason=f"payment {reason}",
            request=request,
        )
        return Outcome.REFUND_REQUIRED

    async def _success(
        self,
        order: Order,
        payment: Payment,
        cart_id: UUID,
        result: VerifyResult,
        request: Request | None,
    ) -> None:
        confirmed = await RedemptionService(self._session).confirm(order.id)
        if confirmed is ConfirmOutcome.RELEASED:
            # The order is pending_payment with a live reservation: its use cannot be gone.
            raise RuntimeError(f"order {order.id}: redemption released before payment")
        await self._remove_ordered_lines(order, cart_id)
        await move_payment(
            self._session,
            payment,
            PaymentStatus.PAID,
            paid_amount=result.amount,
            raw=result.raw,
        )
        moved = await move_order_payment(
            self._session,
            order,
            PaymentStatus.PAID,
            actor_user_id=None,
            reason="payment verified",
            request=request,
        )
        if not moved:
            # Unreachable for a pending_payment order; fail loudly rather than half-apply.
            raise RuntimeError(f"order {order.id}: payment status cannot become paid")
        await OrderStateService(self._session).transition(
            order.id,
            StatusField.ORDER,
            OrderStatus.CONFIRMED,
            actor_user_id=None,
            reason="payment verified",
            request=request,
        )
        await record_audit(
            self._session,
            actor_id=None,
            action="payment.paid",
            entity_type="payment",
            entity_id=payment.id,
            before=None,
            after={"order_number": order.order_number, "amount": payment.amount},
            request=request,
        )
        logger.info(
            "payment.paid",
            extra={"payment_id": str(payment.id), "order_number": order.order_number},
        )

    async def _remove_ordered_lines(self, order: Order, cart_id: UUID) -> None:
        """Take only the ordered quantities out of the cart (D34); later additions stay."""
        ordered: dict[UUID, int] = defaultdict(int)
        for variant_id, quantity in await self._session.execute(
            select(OrderItem.variant_id, OrderItem.quantity).where(OrderItem.order_id == order.id)
        ):
            ordered[variant_id] += quantity
        repository = CartRepository(self._session)
        changed = False
        for variant_id, quantity in sorted(ordered.items()):
            line = await repository.item_for_variant(cart_id, variant_id)
            if line is None:
                continue
            changed = True
            if line.quantity > quantity:
                line.quantity -= quantity
            else:
                await self._session.execute(delete(CartItem).where(CartItem.id == line.id))
        cart = await self._session.get(Cart, cart_id)
        assert cart is not None
        if order.discount_code_id is not None and cart.discount_code_id == order.discount_code_id:
            # The code was used by this order (ADR-051).
            cart.discount_code_id = None
            changed = True
        if changed:
            cart.updated_at = utc_now()
        await self._session.flush()

    async def _reservation_of(self, order_id: UUID) -> UUID | None:
        """The order's active or committed reservation (the unique index allows one)."""
        return await self._session.scalar(
            select(InventoryReservation.id).where(
                InventoryReservation.order_id == order_id,
                InventoryReservation.status.in_(
                    [ReservationStatus.ACTIVE, ReservationStatus.COMMITTED]
                ),
            )
        )

    async def _refund(
        self,
        order: Order,
        payment: Payment,
        result: VerifyResult,
        reason: str,
        request: Request | None,
        *,
        level: int = logging.WARNING,
    ) -> None:
        """Money taken that must go back by hand: audit and log (no PII; D32, ADR-051)."""
        await move_payment(
            self._session,
            payment,
            PaymentStatus.REFUND_REQUIRED,
            reason=reason,
            paid_amount=result.amount,
            raw=result.raw,
        )
        action = (
            "payment.amount_mismatch" if reason == AMOUNT_MISMATCH else "payment.refund_required"
        )
        await record_audit(
            self._session,
            actor_id=None,
            action=action,
            entity_type="payment",
            entity_id=payment.id,
            before=None,
            after={
                "order_number": order.order_number,
                "amount": payment.amount,
                "paid_amount": result.amount,
                "reason": reason,
            },
            request=request,
        )
        logger.log(
            level,
            "payment.refund_required",
            extra={
                "order_number": order.order_number,
                "payment_id": str(payment.id),
                "amount": payment.amount,
                "paid_amount": result.amount,
                "reason": reason,
            },
        )
