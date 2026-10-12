from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any, Final
from uuid import UUID

from sqlalchemy import UnaryExpression
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.core.errors import BusinessRuleError, ConflictError, ForbiddenError, NotFoundError
from app.core.time import utc_now
from app.db.models import User, UserStatus
from app.modules.admin.repository import SUPER_ADMIN_ROLE, AdminUserRepository, UserFilters
from app.modules.admin.schemas import AdminUserResponse
from app.modules.auth.repository import SessionRepository, UserRepository
from app.modules.auth.service import CurrentUser
from app.shared.audit import record_audit
from app.shared.pagination import Page, PageParams

logger = logging.getLogger("app.admin")

# Admins may change the status only of users whose roles are all in this set; anyone
# with a staff role is managed by a super admin alone (ADR-019).
ADMIN_MANAGEABLE_ROLES: Final = frozenset({"customer"})


def _user_not_found() -> NotFoundError:
    return NotFoundError(message="User not found")


def _response(user: User, roles: Sequence[str]) -> AdminUserResponse:
    return AdminUserResponse(
        id=user.id,
        mobile=user.phone,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        status=user.status,
        roles=sorted(roles),
        mobile_verified_at=user.mobile_verified_at,
        created_at=user.created_at,
    )


class AdminUserService:
    """User administration: list, status (activate/deactivate/block) and role changes."""

    def __init__(
        self,
        session: AsyncSession,
        repository: AdminUserRepository,
        user_repository: UserRepository,
        session_repository: SessionRepository,
    ) -> None:
        self._session = session
        self._repository = repository
        self._users = user_repository
        self._sessions = session_repository

    async def list_users(
        self,
        filters: UserFilters,
        order_by: Sequence[UnaryExpression[Any]],
        paging: PageParams,
    ) -> Page[AdminUserResponse]:
        async with self._session.begin():
            users, total = await self._repository.list_users(
                filters, order_by, offset=paging.offset, limit=paging.limit
            )
            roles = await self._repository.roles_of([user.id for user in users])
        items = [_response(user, roles.get(user.id, [])) for user in users]
        return Page.build(items, total=total, params=paging)

    async def change_status(
        self,
        actor: CurrentUser,
        user_id: UUID,
        status: UserStatus,
        audit_request: Request | None,
    ) -> AdminUserResponse:
        """Set a user's status; leaving ``active`` revokes all of the user's sessions."""
        if user_id == actor.id:
            raise BusinessRuleError(message="You cannot change your own status")
        async with self._session.begin():
            # Same lock order as change_roles: the super admin set first, then the user row.
            await self._repository.lock_super_admin_set()
            user = await self._users.lock_active(user_id)
            if user is None:
                raise _user_not_found()
            roles = (await self._repository.roles_of([user.id])).get(user.id, [])
            if not set(roles) <= ADMIN_MANAGEABLE_ROLES and SUPER_ADMIN_ROLE not in actor.roles:
                raise ForbiddenError(message="Only a super admin can manage staff accounts")
            before = user.status
            if before == status:
                return _response(user, roles)

            user.status = status
            await self._session.flush()
            revoked = 0
            if status != UserStatus.ACTIVE:
                revoked = await self._sessions.revoke_user(user.id, utc_now())
                if SUPER_ADMIN_ROLE in roles:
                    await self._ensure_super_admin_remains()
            await record_audit(
                self._session,
                actor_id=actor.id,
                action="user.status_changed",
                entity_type="user",
                entity_id=user.id,
                before={"status": before},
                after={"status": status, "revoked_sessions": revoked},
                request=audit_request,
            )
        logger.info(
            "user.status_changed",
            extra={"user_id": str(user.id), "status": str(status), "revoked_sessions": revoked},
        )
        return _response(user, roles)

    async def change_roles(
        self,
        actor: CurrentUser,
        user_id: UUID,
        roles: Sequence[str],
        audit_request: Request | None,
    ) -> AdminUserResponse:
        """Replace a user's roles with ``roles`` (already limited to DEFAULT_ROLES)."""
        # Checked on the database roles of this request, on top of users:manage_roles.
        if SUPER_ADMIN_ROLE not in actor.roles:
            raise ForbiddenError(message="Only a super admin can change roles")
        if user_id == actor.id:
            raise BusinessRuleError(message="You cannot change your own roles")
        new_roles = sorted(set(roles))
        async with self._session.begin():
            await self._repository.lock_super_admin_set()
            user = await self._users.lock_active(user_id)
            if user is None:
                raise _user_not_found()
            before = (await self._repository.roles_of([user.id])).get(user.id, [])
            if before == new_roles:
                return _response(user, before)

            role_ids = await self._repository.role_ids(new_roles)
            missing = sorted(set(new_roles) - role_ids.keys())
            if missing:
                raise RuntimeError(f"Roles missing from the database: {missing}; run the seed")
            await self._repository.replace_roles(user.id, [role_ids[name] for name in new_roles])
            if SUPER_ADMIN_ROLE in before and SUPER_ADMIN_ROLE not in new_roles:
                await self._ensure_super_admin_remains()
            await record_audit(
                self._session,
                actor_id=actor.id,
                action="user.roles_changed",
                entity_type="user",
                entity_id=user.id,
                before={"roles": before},
                after={"roles": new_roles},
                request=audit_request,
            )
        logger.info("user.roles_changed", extra={"user_id": str(user.id), "roles": new_roles})
        return _response(user, new_roles)

    async def _ensure_super_admin_remains(self) -> None:
        # Unreachable through one request (self-changes are rejected), but two super
        # admins removing each other concurrently would otherwise lock everyone out.
        if await self._repository.count_active_super_admins() == 0:
            raise ConflictError(message="At least one active super admin must remain")
