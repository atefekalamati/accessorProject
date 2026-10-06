from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ColumnElement, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import OtpCode


@dataclass(frozen=True, slots=True)
class WindowUsage:
    """OTP codes issued since a point in time, and the oldest of them."""

    count: int
    oldest: datetime | None


class OtpRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_mobile(self, mobile: str) -> None:
        """Serialize OTP issuance per mobile until the transaction ends."""
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"otp:{mobile}"},
        )

    async def latest_created_at(self, mobile: str) -> datetime | None:
        statement = select(func.max(OtpCode.created_at)).where(OtpCode.mobile == mobile)
        latest: datetime | None = await self._session.scalar(statement)
        return latest

    async def usage_by_mobile(self, mobile: str, since: datetime) -> WindowUsage:
        return await self._usage(since, OtpCode.mobile == mobile)

    async def usage_by_ip(self, ip: str, since: datetime) -> WindowUsage:
        return await self._usage(since, OtpCode.ip == ip)

    async def usage_global(self, since: datetime) -> WindowUsage:
        return await self._usage(since)

    async def _usage(self, since: datetime, *criteria: ColumnElement[bool]) -> WindowUsage:
        statement = select(func.count(), func.min(OtpCode.created_at)).where(
            OtpCode.created_at > since, *criteria
        )
        count, oldest = (await self._session.execute(statement)).one()
        return WindowUsage(count=count, oldest=oldest)

    async def expire_active(self, mobile: str, now: datetime) -> None:
        """Invalidate unconsumed, unexpired codes of ``mobile`` by expiring them now."""
        await self._session.execute(
            update(OtpCode)
            .where(
                OtpCode.mobile == mobile,
                OtpCode.consumed_at.is_(None),
                OtpCode.expires_at > now,
            )
            .values(expires_at=now)
        )

    async def add(self, otp: OtpCode) -> None:
        self._session.add(otp)
        await self._session.flush()
