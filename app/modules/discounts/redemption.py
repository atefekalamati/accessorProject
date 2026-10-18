"""Discount redemptions for orders: redeem, confirm, release (DSC-05, D31, D32, ADR-044).

Internal, like reservations: no public endpoint. ORD-04 calls ``redeem`` while creating an
order, PAY-03 ``confirm`` on a paid callback, ORD/PAY and the expiry job ``release`` on
cancel, reservation expiry or a refund. Everything runs in the caller's transaction and
never commits; ``confirm`` and ``release`` return an outcome and never raise, so a caller
can record related changes (refund_required, cancellation, audit) in the same transaction.

Global lock order for the purchase flow (ADR-044, ADR-046): idempotency key → cart →
order advisory lock →
variants / inventory items → DiscountCode row → redemption row. ``redeem`` locks the code
row and counts the limits only under that lock, so concurrent orders never exceed them;
the admin edit and delete (DSC-04) take the same code lock. ``confirm`` and ``release``
lock only the redemption row: a release only lowers the count, so an uncommitted release
can only make a concurrent ``redeem`` stricter, never let it overshoot.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, ErrorCode
from app.core.phone import MOBILE_E164_PATTERN
from app.core.time import utc_now
from app.db.models import DiscountCode, DiscountRedemption, RedemptionStatus
from app.modules.discounts.repository import DiscountRepository
from app.modules.discounts.rules import CodeRules, Rejection, check_code, discount_error, rules_of
from app.shared.money import MAX_PRICE_TOMAN

logger = logging.getLogger(__name__)

_MOBILE = re.compile(MOBILE_E164_PATTERN)


class ConfirmOutcome(StrEnum):
    CONFIRMED = "confirmed"
    ALREADY_CONFIRMED = "already_confirmed"
    # Released before payment (cancel or expiry): the caller handles it (D32), no raise.
    RELEASED = "released"
    # The order used no code.
    NONE = "none"


class ReleaseOutcome(StrEnum):
    RELEASED = "released"
    ALREADY_RELEASED = "already_released"
    NONE = "none"


def _already_redeemed() -> ConflictError:
    return ConflictError(
        message="The order already has a discount redemption",
        details=[{"field": "code", "type": "order_already_redeemed"}],
    )


def _require_transaction(session: AsyncSession, name: str) -> None:
    if not session.in_transaction():
        raise RuntimeError(f"{name}() must run inside the caller's transaction")


def _check_inputs(phone: str, amount: int, subtotal: int) -> None:
    for name, value in (("amount", amount), ("subtotal", subtotal)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be int")
        if not 0 <= value <= MAX_PRICE_TOMAN:
            raise ValueError(f"{name} is out of range")
    if amount > subtotal:
        raise ValueError("amount cannot exceed the subtotal")
    if not _MOBILE.fullmatch(phone):
        raise ValueError("phone must be a verified E.164 mobile number")


class RedemptionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._discounts = DiscountRepository(session)

    async def lock_code(self, code_id: UUID) -> DiscountCode | None:
        """The code row under FOR UPDATE: ORD-04 takes it before pricing with the code, so
        the rules it prices with are the rules ``redeem`` checks (ADR-044)."""
        statement = (
            select(DiscountCode)
            .where(DiscountCode.id == code_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return (await self._session.scalars(statement)).one_or_none()

    async def redeem(
        self,
        *,
        code_id: UUID,
        priced_rules: CodeRules,
        order_id: UUID,
        user_id: UUID | None,
        phone: str,
        amount: int,
        subtotal: int,
        now: datetime | None = None,
    ) -> DiscountRedemption:
        """A pending redemption that counts toward the limits (D31).

        ``amount`` (the code amount) and ``subtotal`` (the minimum-order basis, ADR-043)
        come only from the caller's ``price_order`` pass with ``priced_rules``; the caller
        skips ``redeem`` when that pass had ``code_applied`` false. Rules changed since
        pricing → 409 PRICE_CHANGED (the caller prices again and then gets the 422). An order
        redeems at most once: a retry with the same code, amount, phone and user returns the
        live redemption, anything else is 409. The caller holds the order's advisory lock;
        without it, a concurrent redeem of the same order with another code still gets 409
        (the live-order unique index), never a 500.
        """
        _require_transaction(self._session, "redeem")
        _check_inputs(phone, amount, subtotal)
        now = now or utc_now()
        code = await self.lock_code(code_id)
        previous = await self._of_order(order_id)
        if previous is not None:
            if previous.status != RedemptionStatus.RELEASED and (
                previous.discount_code_id,
                previous.amount,
                previous.phone,
                previous.user_id,
            ) == (code_id, amount, phone, user_id):
                return previous
            raise _already_redeemed()
        rules = None if code is None else rules_of(code)
        if rules is not None and rules != priced_rules:
            raise ConflictError(
                code=ErrorCode.PRICE_CHANGED,
                message="The discount code changed; price the order again",
                details=[{"field": "code", "type": "code_changed"}],
            )
        usage = await self._discounts.usage(code_id, phone)
        rejection = check_code(rules, at=now, subtotal=subtotal, usage=usage)
        if rejection is not None or code is None:
            raise discount_error(rejection or Rejection.INVALID)
        redemption = DiscountRedemption(
            discount_code_id=code.id,
            order_id=order_id,
            user_id=user_id,
            phone=phone,
            code=code.code,
            amount=amount,
            status=RedemptionStatus.PENDING,
        )
        try:
            async with self._session.begin_nested():
                self._session.add(redemption)
        except IntegrityError as error:
            if "uq_discount_redemptions_live_order" not in str(error.orig):
                raise
            raise _already_redeemed() from error
        logger.info(
            "discount.redeemed",
            extra={"redemption_id": str(redemption.id), "order_id": str(order_id)},
        )
        return redemption

    async def confirm(self, order_id: UUID, now: datetime | None = None) -> ConfirmOutcome:
        """Paid: pending → confirmed. Never raises for a state it finds.

        PAY-03 calls ``release`` instead when the reservation commit says EXPIRED (D32),
        even if this redemption is still pending because no job ran yet.
        """
        _require_transaction(self._session, "confirm")
        redemption = await self._of_order(order_id, lock=True)
        if redemption is None:
            return ConfirmOutcome.NONE
        if redemption.status == RedemptionStatus.RELEASED:
            return ConfirmOutcome.RELEASED
        if redemption.status == RedemptionStatus.CONFIRMED:
            return ConfirmOutcome.ALREADY_CONFIRMED
        redemption.status = RedemptionStatus.CONFIRMED
        redemption.confirmed_at = now or utc_now()
        await self._session.flush()
        return ConfirmOutcome.CONFIRMED

    async def release(self, order_id: UUID, now: datetime | None = None) -> ReleaseOutcome:
        """Cancel, reservation expiry or refund: the use no longer counts. Never raises."""
        _require_transaction(self._session, "release")
        redemption = await self._of_order(order_id, lock=True)
        if redemption is None:
            return ReleaseOutcome.NONE
        if redemption.status == RedemptionStatus.RELEASED:
            return ReleaseOutcome.ALREADY_RELEASED
        released_at = now or utc_now()
        if redemption.confirmed_at is not None:
            # Never before the payment it reverses (CHECK released_after_confirmed).
            released_at = max(released_at, redemption.confirmed_at)
        redemption.status = RedemptionStatus.RELEASED
        redemption.released_at = released_at
        await self._session.flush()
        return ReleaseOutcome.RELEASED

    async def _of_order(self, order_id: UUID, *, lock: bool = False) -> DiscountRedemption | None:
        """The order's redemption; an order redeems at most once (orders are immutable)."""
        statement = select(DiscountRedemption).where(DiscountRedemption.order_id == order_id)
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await self._session.scalars(statement)).one_or_none()
