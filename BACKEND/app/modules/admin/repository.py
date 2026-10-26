from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, UnaryExpression, delete, exists, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Role, User, UserRole, UserStatus
from app.db.models.common import not_deleted

SUPER_ADMIN_ROLE = "super_admin"


@dataclass(frozen=True, slots=True)
class UserFilters:
    mobile_digits: str | None = None
    status: UserStatus | None = None
    role: str | None = None


class AdminUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _criteria(self, filters: UserFilters) -> list[ColumnElement[bool]]:
        criteria: list[ColumnElement[bool]] = [not_deleted(User)]
        if filters.mobile_digits is not None:
            # Digits only (validated by the caller), so no LIKE metacharacters can occur.
            criteria.append(User.phone.contains(filters.mobile_digits))
        if filters.status is not None:
            criteria.append(User.status == filters.status)
        if filters.role is not None:
            criteria.append(
                exists()
                .where(UserRole.user_id == User.id, UserRole.role_id == Role.id)
                .where(Role.name == filters.role)
            )
        return criteria

    async def list_users(
        self,
        filters: UserFilters,
        order_by: Sequence[UnaryExpression[Any]],
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[User], int]:
        criteria = self._criteria(filters)
        total = await self._session.scalar(select(func.count()).select_from(User).where(*criteria))
        statement = select(User).where(*criteria).order_by(*order_by).offset(offset).limit(limit)
        users = list((await self._session.scalars(statement)).all())
        return users, total or 0

    async def roles_of(self, user_ids: Sequence[UUID]) -> dict[UUID, list[str]]:
        roles: dict[UUID, list[str]] = defaultdict(list)
        if not user_ids:
            return roles
        statement = (
            select(UserRole.user_id, Role.name)
            .join(Role, Role.id == UserRole.role_id)
            .where(UserRole.user_id.in_(user_ids))
            .order_by(Role.name)
        )
        for user_id, name in (await self._session.execute(statement)).all():
            roles[user_id].append(name)
        return roles

    async def lock_super_admin_set(self) -> None:
        """Serialize every change that can remove a super admin until the transaction ends."""
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": "rbac:super_admin"},
        )

    async def count_active_super_admins(self) -> int:
        statement = (
            select(func.count(func.distinct(User.id)))
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(
                Role.name == SUPER_ADMIN_ROLE,
                User.status == UserStatus.ACTIVE,
                not_deleted(User),
            )
        )
        return await self._session.scalar(statement) or 0

    async def role_ids(self, names: Sequence[str]) -> dict[str, UUID]:
        statement = select(Role.name, Role.id).where(Role.name.in_(names))
        return {name: role_id for name, role_id in (await self._session.execute(statement)).all()}

    async def replace_roles(self, user_id: UUID, role_ids: Sequence[UUID]) -> None:
        await self._session.execute(delete(UserRole).where(UserRole.user_id == user_id))
        self._session.add_all(UserRole(user_id=user_id, role_id=role_id) for role_id in role_ids)
        await self._session.flush()
