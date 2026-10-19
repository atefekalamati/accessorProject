"""POST /payments/init: start (or resume) paying an order (PAY-02, ADR-049, ADR-051).

Never holds a lock across a gateway call, so init runs in short transactions:

1. Prepare (one transaction): idempotency key → ownership (404) → order advisory → order
   row. The order must be ``pending_payment`` with a live reservation (an expired one
   cancels the order lazily, ADR-050, then 409 after the commit) and enough time left.
   An existing pending payment is resumed while its gateway session is valid (same
   ``redirect_url``), superseded once it is not, or reported as in progress while its
   gateway request is in flight. Otherwise a pending payment of ``grand_total`` is
   inserted with no reference yet, and the order's payment status becomes ``pending``.
2. The gateway request, outside any transaction (bounded by a timeout).
3. Finish (one transaction): the same locks again; the payment must still be pending
   without a reference. The reference, redirect and session expiry are stored and the
   response is saved for the idempotency key.

A gateway that does not answer closes the payment as ``failed`` (``gateway_error``) and
answers 503; the order stays payable. A duplicate with the same key during step 2 gets
409 ``PAYMENT_IN_PROGRESS`` (its response is not stored yet). A key replays its first
201 for 24 hours, even after that session ended: a new attempt needs a new key.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Final
from uuid import UUID

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError, BusinessRuleError, ConflictError, ErrorCode, NotFoundError
from app.core.time import utc_now
from app.db.models import (
    CancelReason,
    InventoryReservation,
    Order,
    OrderStatus,
    Payment,
    PaymentStatus,
    ReservationStatus,
)
from app.db.models.payments import PaymentEventKind
from app.modules.orders.cancel import OrderCancellation
from app.modules.payments.common import (
    lock_order_row,
    lock_payment,
    move_order_payment,
    move_payment,
    pending_payment_of,
    record_event,
)
from app.modules.payments.gateways.base import (
    GatewayRequest,
    GatewayUnavailable,
    PaymentGateway,
    VerifyOutcome,
    VerifyResult,
)
from app.modules.payments.schemas import InitPaymentRequest, PaymentInitResponse
from app.shared.audit import record_audit
from app.shared.idempotency import IdempotencyService, request_hash

logger = logging.getLogger(__name__)

SCOPE: Final = "payments.init"


@dataclass(frozen=True, slots=True)
class InitResult:
    status_code: int
    body: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _Fresh:
    payment_id: UUID
    amount: int


@dataclass(frozen=True, slots=True)
class _Supersede:
    payment_id: UUID
    reference: str
    amount: int


@dataclass(frozen=True, slots=True)
class _Done:
    result: InitResult


class _Expired(Exception):
    """The reservation expired: the order was cancelled; 409 once that is committed."""


def _in_progress(payment_id: UUID, kind: str) -> ConflictError:
    return ConflictError(
        code=ErrorCode.PAYMENT_IN_PROGRESS,
        message="A payment for this order is in progress",
        details=[{"type": kind, "payment_id": str(payment_id)}],
    )


def _reservation_expired(kind: str) -> ConflictError:
    return ConflictError(
        code=ErrorCode.RESERVATION_EXPIRED,
        message="The order's reservation has expired",
        details=[{"type": kind}],
    )


def gateway_unavailable() -> AppError:
    return AppError(
        code=ErrorCode.PAYMENT_GATEWAY_UNAVAILABLE,
        message="The payment gateway is unavailable; try again shortly",
    )


async def call_gateway[R](call: Awaitable[R], seconds: float) -> R:
    """Await a gateway call bounded by ``seconds``; a network failure is ``GatewayUnavailable``."""
    try:
        async with asyncio.timeout(seconds):
            return await call
    except (TimeoutError, OSError) as error:
        raise GatewayUnavailable(str(error) or type(error).__name__) from error


class PaymentService:
    def __init__(self, session: AsyncSession, gateway: PaymentGateway, settings: Settings) -> None:
        self._session = session
        self._gateway = gateway
        self._settings = settings

    async def init(
        self,
        user_id: UUID,
        key: str,
        payload: InitPaymentRequest,
        request: Request | None = None,
    ) -> InitResult:
        hash_ = request_hash(body=payload.model_dump(mode="json"))
        # One supersede round at most: the new payment's session is fresh.
        for _ in range(2):
            try:
                step = await self._prepare(user_id, key, hash_, payload.order_id, request)
            except _Expired:
                raise _reservation_expired("reservation_expired") from None
            if isinstance(step, _Done):
                return step.result
            if isinstance(step, _Fresh):
                return await self._request(user_id, key, hash_, step, request)
            await self._supersede(step, request)
        raise _in_progress(payload.order_id, "superseding")

    # --- step 1 ----------------------------------------------------------------------

    async def _prepare(
        self,
        user_id: UUID,
        key: str,
        hash_: str,
        order_id: UUID,
        request: Request | None,
    ) -> _Fresh | _Supersede | _Done:
        expired = False
        async with self._session.begin():
            idempotency = IdempotencyService(self._session)
            stored = await idempotency.begin(
                user_id=user_id, scope=SCOPE, key=key, request_hash=hash_
            )
            if stored is not None:
                return _Done(InitResult(stored.status_code, stored.body))
            order = await self._owned_order(user_id, order_id)
            now = utc_now()
            reservation = await self._live_reservation(order)
            if reservation is None or reservation.expires_at <= now:
                await OrderCancellation(self._session).cancel_locked(
                    order, actor_user_id=user_id, request=request
                )
                expired = True
            else:
                step = await self._payment_step(
                    user_id, key, hash_, order, reservation, now, request
                )
        if expired:
            raise _Expired
        return step

    async def _owned_order(self, user_id: UUID, order_id: UUID) -> Order:
        # Ownership before the advisory lock: no contention on other users' order keys.
        owned = await self._session.scalar(
            select(Order.id).where(Order.id == order_id, Order.user_id == user_id)
        )
        order = (
            None
            if owned is None
            else await lock_order_row(self._session, order_id, user_id=user_id)
        )
        if order is None:
            raise NotFoundError(message="Order not found")
        if order.status == OrderStatus.CANCELLED and order.cancel_reason == CancelReason.EXPIRED:
            # The answer the lazy cancel gives (and its same-key retry), whoever cancelled.
            raise _reservation_expired("reservation_expired")
        if order.status != OrderStatus.PENDING_PAYMENT:
            raise BusinessRuleError(
                code=ErrorCode.INVALID_STATE_TRANSITION,
                message="This order cannot be paid",
                details=[{"field": "order", "from": order.status, "type": "order_not_payable"}],
            )
        if order.grand_total <= 0:
            # Nothing to charge; confirming a free order without a gateway is deferred.
            raise BusinessRuleError(
                message="This order has nothing to pay",
                details=[{"field": "order", "type": "zero_amount"}],
            )
        return order

    async def _live_reservation(self, order: Order) -> InventoryReservation | None:
        statement = select(InventoryReservation).where(
            InventoryReservation.order_id == order.id,
            InventoryReservation.status == ReservationStatus.ACTIVE,
        )
        return (await self._session.scalars(statement)).one_or_none()

    async def _payment_step(
        self,
        user_id: UUID,
        key: str,
        hash_: str,
        order: Order,
        reservation: InventoryReservation,
        now: datetime,
        request: Request | None,
    ) -> _Fresh | _Supersede | _Done:
        existing = await pending_payment_of(self._session, order.id)
        if existing is not None:
            if existing.gateway_reference is None:
                stale = timedelta(seconds=self._settings.payment_pending_stale_seconds)
                if now - existing.created_at < stale:
                    raise _in_progress(existing.id, "request_in_flight")
                # The request never came back (crash or lost answer): nothing to verify.
                await self._close(existing, order, "request_lost", request)
            elif existing.gateway_expires_at is not None and existing.gateway_expires_at > now:
                # The customer left the gateway's page: resume the same session (ADR-051).
                result = InitResult(201, _body(existing, order, reservation))
                await IdempotencyService(self._session).complete(
                    user_id=user_id,
                    scope=SCOPE,
                    key=key,
                    request_hash=hash_,
                    status_code=201,
                    body=result.body,
                )
                return _Done(result)
            else:
                return _Supersede(existing.id, existing.gateway_reference, existing.amount)
        remaining = reservation.expires_at - now
        if remaining < timedelta(seconds=self._settings.payment_min_remaining_seconds):
            # The payment would almost surely land after the reservation (refund_required).
            raise _reservation_expired("too_late")
        payment = Payment(
            order_id=order.id,
            gateway=self._gateway.name,
            idempotency_key=key,
            amount=order.grand_total,
            status=PaymentStatus.PENDING,
        )
        self._session.add(payment)
        await self._session.flush()
        await move_order_payment(
            self._session,
            order,
            PaymentStatus.PENDING,
            actor_user_id=user_id,
            reason="payment started",
            request=request,
        )
        await record_audit(
            self._session,
            actor_id=user_id,
            action="payment.created",
            entity_type="payment",
            entity_id=payment.id,
            before=None,
            after={
                "order_number": order.order_number,
                "amount": payment.amount,
                "gateway": payment.gateway,
            },
            request=request,
        )
        return _Fresh(payment.id, payment.amount)

    async def _close(
        self, payment: Payment, order: Order, reason: str, request: Request | None
    ) -> None:
        """Close a locked pending payment as failed; the order may start a new one."""
        await move_payment(self._session, payment, PaymentStatus.FAILED, reason=reason)
        await move_order_payment(
            self._session,
            order,
            PaymentStatus.FAILED,
            actor_user_id=None,
            reason=f"payment {reason}",
            request=request,
        )

    # --- supersede an expired gateway session ----------------------------------------

    async def _supersede(self, step: _Supersede, request: Request | None) -> None:
        """Verify the old payment, then close it if the gateway has not taken money."""
        try:
            result: VerifyResult = await call_gateway(
                self._gateway.verify(reference=step.reference, amount=step.amount),
                self._settings.payment_gateway_timeout_seconds,
            )
        except GatewayUnavailable:
            logger.warning(
                "payment.gateway_unavailable", extra={"payment_id": str(step.payment_id)}
            )
            raise gateway_unavailable() from None
        async with self._session.begin():
            payment = await self._session.get(Payment, step.payment_id)
            assert payment is not None
            order = await lock_order_row(self._session, payment.order_id)
            payment = await lock_payment(self._session, step.payment_id)
            assert order is not None and payment is not None
            await record_event(
                self._session,
                gateway=payment.gateway,
                kind=PaymentEventKind.VERIFY,
                payload=result.raw,
                reference=step.reference,
                payment_id=payment.id,
            )
            # Only a final FAILED closes it (ADR-051). PAID: its callback or reconciliation
            # applies it (PAY-03). PENDING: the gateway still accepts the old session, so a
            # new one could charge the customer twice; wait for it instead.
            still_open = (
                payment.status == PaymentStatus.PENDING
                and result.outcome is not VerifyOutcome.FAILED
            )
            if payment.status == PaymentStatus.PENDING and not still_open:
                await self._close(payment, order, result.failure_reason or "superseded", request)
        if still_open:
            kind = "payment_confirming" if result.outcome is VerifyOutcome.PAID else "session_open"
            raise _in_progress(step.payment_id, kind)

    # --- steps 2 and 3 ---------------------------------------------------------------

    async def _request(
        self,
        user_id: UUID,
        key: str,
        hash_: str,
        fresh: _Fresh,
        request: Request | None,
    ) -> InitResult:
        try:
            answer: GatewayRequest = await call_gateway(
                self._gateway.request(
                    payment_id=fresh.payment_id,
                    amount=fresh.amount,
                    callback_url=self._settings.payment_callback_url,
                ),
                self._settings.payment_gateway_timeout_seconds,
            )
        except GatewayUnavailable:
            logger.warning(
                "payment.gateway_unavailable", extra={"payment_id": str(fresh.payment_id)}
            )
            await self._fail_request(fresh.payment_id, request)
            raise gateway_unavailable() from None
        except Exception:
            # An adapter bug must not leave the order stuck behind a pending payment.
            logger.exception(
                "payment.gateway_request_failed", extra={"payment_id": str(fresh.payment_id)}
            )
            await self._fail_request(fresh.payment_id, request)
            raise
        async with self._session.begin():
            idempotency = IdempotencyService(self._session)
            stored = await idempotency.begin(
                user_id=user_id, scope=SCOPE, key=key, request_hash=hash_
            )
            if stored is not None:
                return InitResult(stored.status_code, stored.body)
            payment = await self._session.get(Payment, fresh.payment_id)
            assert payment is not None
            order = await lock_order_row(self._session, payment.order_id)
            payment = await lock_payment(self._session, fresh.payment_id)
            assert order is not None and payment is not None
            if payment.status != PaymentStatus.PENDING or payment.gateway_reference is not None:
                # Closed meanwhile (reconciliation's request_lost): nothing is stored.
                raise _in_progress(payment.id, "request_superseded")
            payment.gateway_reference = answer.reference
            payment.redirect_url = answer.redirect_url
            payment.gateway_expires_at = answer.expires_at
            await self._session.flush()
            reservation = await self._live_reservation(order)
            if (
                order.status != OrderStatus.PENDING_PAYMENT
                or reservation is None
                or reservation.expires_at <= utc_now()
            ):
                # Cancelled or expired during the gateway call: close the unused session.
                await self._close(payment, order, "reservation_expired", request)
                closed = True
            else:
                closed = False
                result = InitResult(201, _body(payment, order, reservation))
                await idempotency.complete(
                    user_id=user_id,
                    scope=SCOPE,
                    key=key,
                    request_hash=hash_,
                    status_code=201,
                    body=result.body,
                )
        if closed:
            raise _reservation_expired("reservation_expired")
        logger.info(
            "payment.started",
            extra={"payment_id": str(fresh.payment_id), "order_number": order.order_number},
        )
        return result

    async def _fail_request(self, payment_id: UUID, request: Request | None) -> None:
        async with self._session.begin():
            payment = await self._session.get(Payment, payment_id)
            assert payment is not None
            order = await lock_order_row(self._session, payment.order_id)
            payment = await lock_payment(self._session, payment_id)
            assert order is not None and payment is not None
            if payment.status == PaymentStatus.PENDING and payment.gateway_reference is None:
                await self._close(payment, order, "gateway_error", request)


def _body(payment: Payment, order: Order, reservation: InventoryReservation) -> dict[str, Any]:
    assert payment.redirect_url is not None and payment.gateway_expires_at is not None
    return PaymentInitResponse(
        payment_id=payment.id,
        order_id=order.id,
        order_number=order.order_number,
        amount=payment.amount,
        currency=order.currency,
        redirect_url=payment.redirect_url,
        gateway_expires_at=payment.gateway_expires_at,
        reservation_expires_at=reservation.expires_at,
    ).model_dump(mode="json")
