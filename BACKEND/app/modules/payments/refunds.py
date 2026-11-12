"""Recording a manual refund: refund_required → refunded (ADM-08, D35, ADR-054).

Staff give the money back outside the system (bank transfer) and record it here. Only a
full refund exists in v1: the gateway-confirmed ``paid_amount``, or, when the gateway's
figure is unknown (not a whole toman), the amount staff enter (≤ the order total).

Lock order (ADR-048): the order's advisory lock, the order row, then the payment row,
the same as the payment callback; nothing else is locked.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.time import utc_now
from app.db.models import Order, Payment, PaymentStatus, StatusField
from app.db.models.payments import RefundAmountSource
from app.modules.orders.state_service import invalid_transition
from app.modules.payments.common import lock_order_row, lock_payment, move_order_payment
from app.shared.audit import record_audit

logger = logging.getLogger(__name__)

_UNIQUE_REFERENCE = "uq_payments_refund_reference"


def _reference_taken() -> ConflictError:
    return ConflictError(
        message="This refund reference is already recorded on another payment",
        details=[{"field": "refund_reference", "type": "refund_reference_taken"}],
    )


def _amount_error(kind: str, message: str) -> BusinessRuleError:
    return BusinessRuleError(message=message, details=[{"field": "amount", "type": kind}])


class RefundService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        actor_id: UUID,
        payment_id: UUID,
        *,
        reference: str,
        amount: int | None,
        note: str | None,
        request: Request | None,
    ) -> UUID:
        """Mark the payment refunded; returns its order id. Idempotent per reference."""
        async with self._session.begin():
            order_id = await self._session.scalar(
                select(Payment.order_id).where(Payment.id == payment_id)
            )
            if order_id is None:
                raise NotFoundError(message="Payment not found")
            order = await lock_order_row(self._session, order_id)
            payment = await lock_payment(self._session, payment_id)
            if order is None or payment is None:  # rows are never deleted
                raise RuntimeError(f"payment {payment_id} or its order vanished")

            if payment.status == PaymentStatus.REFUNDED:
                if payment.refund_reference == reference:
                    return order_id  # the same request again: nothing to do
                raise ConflictError(
                    message="This payment is already refunded under another reference",
                    details=[{"type": "already_refunded"}],
                )
            if payment.status != PaymentStatus.REFUND_REQUIRED:
                raise invalid_transition(
                    StatusField.PAYMENT, payment.status, PaymentStatus.REFUNDED, "not_allowed"
                )
            refund_amount, source = self._amount(payment, order, amount)
            taken = await self._session.scalar(
                select(
                    exists().where(Payment.refund_reference == reference, Payment.id != payment.id)
                )
            )
            if taken:
                raise _reference_taken()

            now = utc_now()
            payment.status = PaymentStatus.REFUNDED
            payment.refund_reference = reference
            payment.refund_amount = refund_amount
            payment.refund_amount_source = source
            payment.refunded_at = now
            payment.refunded_by = actor_id
            try:
                # A savepoint: a concurrent use of the same reference fails only this flush.
                async with self._session.begin_nested():
                    await self._session.flush()
            except IntegrityError as error:
                if _UNIQUE_REFERENCE in str(error.orig):
                    raise _reference_taken() from error
                raise

            after: dict[str, Any] = {
                "status": PaymentStatus.REFUNDED.value,
                "refund_reference": reference,
                "refund_amount": refund_amount,
                "refund_amount_source": source,
                "paid_amount": payment.paid_amount,
            }
            if note is not None:
                after["note"] = note
            await record_audit(
                self._session,
                actor_id=actor_id,
                action="payment.refunded",
                entity_type="payment",
                entity_id=payment.id,
                before={"status": PaymentStatus.REFUND_REQUIRED.value},
                after=after,
                request=request,
            )
            await self._settle_order(order, payment, actor_id, request)
        logger.info(
            "payment.refunded",
            extra={"payment_id": str(payment_id), "amount": refund_amount, "source": source},
        )
        return order_id

    def _amount(self, payment: Payment, order: Order, amount: int | None) -> tuple[int, str]:
        """The full refund: the gateway's figure, or staff's when the gateway's is unknown."""
        if payment.paid_amount == 0:
            # The gateway confirmed it took nothing (a wrong-amount PAID of 0).
            raise _amount_error("nothing_to_refund", "The gateway took no money for this payment")
        if payment.paid_amount is not None:
            if amount is not None:
                raise _amount_error(
                    "amount_not_allowed",
                    "The gateway confirmed the amount; the whole of it is refunded",
                )
            return payment.paid_amount, RefundAmountSource.GATEWAY
        if amount is None:
            raise _amount_error(
                "amount_required", "The gateway amount is unknown: enter the amount refunded"
            )
        if amount > order.grand_total:
            raise _amount_error("amount_too_large", "The amount exceeds the order total")
        return amount, RefundAmountSource.ADMIN_ENTERED

    async def _settle_order(
        self, order: Order, payment: Payment, actor_id: UUID, request: Request | None
    ) -> None:
        """The order is refunded once none of its payments is still owed (D35)."""
        if order.payment_status != PaymentStatus.REFUND_REQUIRED:
            return  # e.g. a duplicate payment on a paid order: only the row moves
        still_owed = await self._session.scalar(
            select(
                exists().where(
                    Payment.order_id == order.id,
                    Payment.id != payment.id,
                    Payment.status == PaymentStatus.REFUND_REQUIRED,
                )
            )
        )
        if still_owed:
            return
        await move_order_payment(
            self._session,
            order,
            PaymentStatus.REFUNDED,
            actor_user_id=actor_id,
            reason="refund recorded",
            request=request,
        )
