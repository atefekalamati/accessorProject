from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import Permission, Role, RolePermission
from app.db.session import create_database_engine, create_session_factory


@dataclass(frozen=True, slots=True)
class RoleSeed:
    name: str
    description: str


@dataclass(frozen=True, slots=True)
class PermissionSeed:
    key: str
    description: str

    @property
    def module(self) -> str:
        return self.key.split(":", 1)[0]


# Database roles per ADR-004; guest is not a database role.
DEFAULT_ROLES: tuple[RoleSeed, ...] = (
    RoleSeed("customer", "Store customer"),
    RoleSeed("support", "Customer support agent"),
    RoleSeed("content_manager", "Content manager"),
    RoleSeed("admin", "Store administrator"),
    RoleSeed("super_admin", "Super administrator; manages roles and sensitive settings"),
)

# Permission keys use the `<module>:<action>` format.
PERMISSIONS: tuple[PermissionSeed, ...] = (
    PermissionSeed("catalog:manage", "Manage products, variants, categories and collections"),
    PermissionSeed(
        "categories:edit_content",
        "Edit category title, description, banner and display order (ADR-023)",
    ),
    PermissionSeed("pricing:update", "Change product and variant prices"),
    PermissionSeed("pricing_settings:update", "Change tax and rounding settings"),
    PermissionSeed("inventory:read", "View stock levels"),
    PermissionSeed("inventory:update", "Change stock levels"),
    PermissionSeed("discounts:manage", "Manage discount codes"),
    PermissionSeed("shipping:manage", "Manage shipping methods and their costs"),
    PermissionSeed("orders:read", "View orders"),
    PermissionSeed("orders:update_status", "Change order and shipment status"),
    PermissionSeed("payments:refund", "Record a manual refund of a payment (ADM-08)"),
    PermissionSeed("customers:read", "View customers"),
    PermissionSeed("content:manage", "Manage banners, sections and static content"),
    PermissionSeed("contact_messages:manage", "Read and handle contact messages"),
    PermissionSeed("users:read", "View users"),
    PermissionSeed("users:manage", "Activate, deactivate or block users"),
    PermissionSeed("users:manage_roles", "Change user roles"),
    PermissionSeed("audit:read", "View the audit log"),
    PermissionSeed("reports:read", "View reports"),
)

ALL_PERMISSION_KEYS: frozenset[str] = frozenset(permission.key for permission in PERMISSIONS)

# Admins may manage customer accounts (users:manage); the admin service limits them to
# targets whose roles are all customer (ADR-019).
_ADMIN_EXCLUDED: frozenset[str] = frozenset(
    {"pricing_settings:update", "users:manage_roles", "audit:read"}
)

# Customers have no permissions; their access is enforced by ownership checks.
ROLE_PERMISSIONS: Mapping[str, frozenset[str]] = {
    "customer": frozenset(),
    "support": frozenset({"orders:read", "customers:read", "contact_messages:manage"}),
    "content_manager": frozenset({"content:manage", "categories:edit_content"}),
    "admin": ALL_PERMISSION_KEYS - _ADMIN_EXCLUDED,
    "super_admin": ALL_PERMISSION_KEYS,
}


def role_id(name: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"project-ak:role:{name}")


def permission_id(key: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"project-ak:permission:{key}")


async def seed_roles(session: AsyncSession, roles: Sequence[RoleSeed] = DEFAULT_ROLES) -> None:
    rows = [
        {
            "id": role_id(role.name),
            "name": role.name,
            "description": role.description,
            "is_system": True,
        }
        for role in roles
    ]
    statement = insert(Role).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=[Role.name],
        set_={
            "description": statement.excluded.description,
            "is_system": True,
        },
    )
    await session.execute(statement)


async def seed_permissions(
    session: AsyncSession, permissions: Sequence[PermissionSeed] = PERMISSIONS
) -> None:
    rows = [
        {
            "id": permission_id(permission.key),
            "key": permission.key,
            "description": permission.description,
            "module": permission.module,
        }
        for permission in permissions
    ]
    statement = insert(Permission).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=[Permission.key],
        set_={
            "description": statement.excluded.description,
            "module": statement.excluded.module,
        },
    )
    await session.execute(statement)


async def seed_role_permissions(
    session: AsyncSession, mapping: Mapping[str, frozenset[str]] = ROLE_PERMISSIONS
) -> None:
    """Grant the mapped permissions; never revokes grants that are no longer listed."""
    rows = [
        {"role_id": role_id(role), "permission_id": permission_id(key)}
        for role, keys in mapping.items()
        for key in sorted(keys)
    ]
    if not rows:
        return
    statement = insert(RolePermission).values(rows).on_conflict_do_nothing()
    await session.execute(statement)


async def seed_rbac(session: AsyncSession) -> None:
    await seed_roles(session)
    await seed_permissions(session)
    await seed_role_permissions(session)


async def seed_database() -> None:
    engine = create_database_engine(get_settings())
    session_factory = create_session_factory(engine)
    try:
        async with session_factory.begin() as session:
            await seed_rbac(session)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_database())
