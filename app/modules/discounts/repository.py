"""Discount code reads and the failed-attempt log (DSC-03, ADR-042, ADR-043)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import ColumnElement, delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    DiscountAttempt,
    DiscountCode,
    DiscountRedemption,
    RedemptionStatus,
    User,
)
from app.modules.discounts.rules import Usage

_LIVE = (RedemptionStatus.PENDING, RedemptionStatus.CONFIRMED)


@dataclass(frozen=True, slots=True)
class AttemptCount:
    count: int
    # When the scope drops back below its cap: the attempt whose expiry frees the first
    # slot (the (count - cap + 1)-th oldest); None while under the cap.
    frees_at: datetime | None


# Old rows are purged in small batches, skipping rows another request is deleting.
PURGE_BATCH = 500


class DiscountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def live_code(self, normalized: str) -> DiscountCode | None:
        """A non-deleted code by its stored text (inactive ones too: rules decide)."""
        statement = select(DiscountCode).where(
            DiscountCode.code == normalized, DiscountCode.deleted_at.is_(None)
        )
        return (await self._session.scalars(statement)).one_or_none()

    async def usage(self, code_id: UUID, phone: str | None) -> Usage:
        """Live redemptions of a code, in total and for ``phone``, in one query."""
        live = DiscountRedemption.status.in_(_LIVE)
        mine: ColumnElement[bool] = DiscountRedemption.phone == phone
        statement = select(
            func.count().filter(live),
            func.count().filter(live, mine),
        ).where(DiscountRedemption.discount_code_id == code_id)
        total, user = (await self._session.execute(statement)).one()
        return Usage(total_live=int(total), user_live=None if phone is None else int(user))

    async def phone_of(self, user_id: UUID) -> str | None:
        return await self._session.scalar(select(User.phone).where(User.id == user_id))

    async def lock_ip(self, ip: str) -> None:
        """Serialize the per-IP count until the transaction ends (like OTP issuance)."""
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"discount-ip:{ip}"},
        )

    async def failures(
        self, since: datetime, cap: int, *criteria: ColumnElement[bool]
    ) -> AttemptCount:
        window = (DiscountAttempt.created_at > since, *criteria)
        count = int(
            await self._session.scalar(
                select(func.count()).select_from(DiscountAttempt).where(*window)
            )
            or 0
        )
        if count < cap:
            return AttemptCount(count, None)
        frees_at = await self._session.scalar(
            select(DiscountAttempt.created_at)
            .where(*window)
            .order_by(DiscountAttempt.created_at)
            .offset(count - cap)
            .limit(1)
        )
        return AttemptCount(count, frees_at)

    async def usage_for_user(self, code_id: UUID, user_id: UUID | None) -> Usage:
        """Usage with the signed-in user's mobile number; a guest has none (ADR-043)."""
        phone = None if user_id is None else await self.phone_of(user_id)
        return await self.usage(code_id, phone)

    async def record_failure(
        self,
        *,
        cart_id: UUID | None,
        user_id: UUID | None,
        ip: str | None,
        now: datetime,
        purge_before: datetime,
    ) -> None:
        self._session.add(DiscountAttempt(cart_id=cart_id, user_id=user_id, ip=ip, created_at=now))
        # Retention: rows past the window no longer count anywhere. A bounded batch with
        # SKIP LOCKED, so concurrent failures never wait on (or deadlock over) one purge.
        batch = (
            select(DiscountAttempt.id)
            .where(DiscountAttempt.created_at <= purge_before)
            .order_by(DiscountAttempt.created_at)
            .limit(PURGE_BATCH)
            .with_for_update(skip_locked=True)
        )
        await self._session.execute(delete(DiscountAttempt).where(DiscountAttempt.id.in_(batch)))
        await self._session.flush()
