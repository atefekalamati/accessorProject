from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import ColumnElement, exists, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    OtpCode,
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
    UserSession,
    UserStatus,
)
from app.db.models.common import not_deleted


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

    async def lock_latest_unconsumed(self, mobile: str) -> OtpCode | None:
        """The newest unconsumed code of ``mobile``, row-locked until the transaction ends.

        Request-otp expires older codes, so only the newest one can still be valid.
        """
        statement = (
            select(OtpCode)
            .where(OtpCode.mobile == mobile, OtpCode.consumed_at.is_(None))
            .order_by(OtpCode.created_at.desc())
            .limit(1)
            .with_for_update()
        )
        otp: OtpCode | None = await self._session.scalar(statement)
        return otp

    async def consume(self, otp_id: UUID, now: datetime) -> bool:
        """Mark a code consumed; False when it was already consumed (single use)."""
        result = await self._session.execute(
            update(OtpCode)
            .where(OtpCode.id == otp_id, OtpCode.consumed_at.is_(None))
            .values(consumed_at=now)
            .returning(OtpCode.id)
        )
        return result.scalar_one_or_none() is not None


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_phone(self, phone: str) -> User | None:
        """The account that currently owns ``phone`` (soft-deleted accounts excluded)."""
        statement = select(User).where(User.phone == phone, not_deleted(User))
        user: User | None = await self._session.scalar(statement)
        return user

    async def get(self, user_id: UUID) -> User | None:
        user: User | None = await self._session.get(User, user_id)
        return user

    async def has_deleted_blocked(self, phone: str) -> bool:
        """True when a soft-deleted account of ``phone`` was blocked (ADR-017)."""
        statement = select(
            exists().where(
                User.phone == phone,
                User.deleted_at.is_not(None),
                User.status == UserStatus.BLOCKED,
            )
        )
        return bool(await self._session.scalar(statement))

    async def role_id(self, name: str) -> UUID | None:
        role_id: UUID | None = await self._session.scalar(select(Role.id).where(Role.name == name))
        return role_id

    async def lock_active(self, user_id: UUID) -> User | None:
        """A not-deleted user, row-locked until the transaction ends."""
        statement = select(User).where(User.id == user_id, not_deleted(User)).with_for_update()
        user: User | None = await self._session.scalar(statement)
        return user

    async def get_with_session(
        self, user_id: UUID, session_id: UUID
    ) -> tuple[User, UserSession] | None:
        """A user together with one of their sessions; soft-deleted users included."""
        statement = (
            select(User, UserSession)
            .join(UserSession, UserSession.user_id == User.id)
            .where(User.id == user_id, UserSession.id == session_id)
        )
        row = (await self._session.execute(statement)).one_or_none()
        return None if row is None else (row[0], row[1])

    async def role_names(self, user_id: UUID) -> list[str]:
        statement = (
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
            .order_by(Role.name)
        )
        return list((await self._session.scalars(statement)).all())

    async def permission_keys(self, user_id: UUID) -> list[str]:
        """Union of the permissions of all roles of ``user_id``."""
        statement = (
            select(Permission.key)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(UserRole, UserRole.role_id == RolePermission.role_id)
            .where(UserRole.user_id == user_id)
            .distinct()
            .order_by(Permission.key)
        )
        return list((await self._session.scalars(statement)).all())

    async def add_with_role(self, user: User, role_id: UUID) -> None:
        self._session.add(user)
        await self._session.flush()
        self._session.add(UserRole(user_id=user.id, role_id=role_id))
        await self._session.flush()


class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, user_session: UserSession) -> None:
        self._session.add(user_session)
        await self._session.flush()

    async def lock_by_token_hash(self, token_hash: str) -> UserSession | None:
        statement = (
            select(UserSession)
            .where(UserSession.refresh_token_hash == token_hash)
            .with_for_update()
        )
        user_session: UserSession | None = await self._session.scalar(statement)
        return user_session

    async def revoke_family(self, family_id: UUID, now: datetime) -> int:
        """Revoke every still-active session of a family; returns how many were revoked."""
        result = await self._session.execute(
            update(UserSession)
            .where(UserSession.family_id == family_id, UserSession.revoked_at.is_(None))
            .values(revoked_at=now)
            .returning(UserSession.id)
        )
        return len(result.scalars().all())
