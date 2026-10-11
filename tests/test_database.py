from __future__ import annotations

import asyncio
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, inspect, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from alembic import command
from app.core.config import Environment, Settings
from app.core.time import utc_now
from app.db.base import Base
from app.db.models import (
    Address,
    AuditLog,
    OtpCode,
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)
from app.db.models.common import not_deleted
from app.db.seed import (
    ALL_PERMISSION_KEYS,
    DEFAULT_ROLES,
    PERMISSIONS,
    ROLE_PERMISSIONS,
    seed_rbac,
)
from app.main import create_app
from app.modules.auth.otp import hash_otp_code

pytestmark = pytest.mark.integration

HEAD_REVISION = "20261011_0014"

EXPECTED_TABLES = {
    "addresses",
    "alembic_version",
    "app_settings",
    "audit_logs",
    "categories",
    "category_filters",
    "inventory_items",
    "inventory_movements",
    "media",
    "otp_codes",
    "permissions",
    "pricing_settings",
    "product_attributes",
    "product_media",
    "product_variants",
    "products",
    "role_permissions",
    "roles",
    "sessions",
    "user_roles",
    "users",
    "variant_options",
    "warehouses",
}


async def test_migration_cycle_created_expected_schema(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as connection:
        tables = await connection.run_sync(
            lambda sync_connection: set(inspect(sync_connection).get_table_names())
        )
        users_columns = await connection.run_sync(
            lambda sync_connection: {
                column["name"] for column in inspect(sync_connection).get_columns("users")
            }
        )
        addresses_columns = await connection.run_sync(
            lambda sync_connection: {
                column["name"] for column in inspect(sync_connection).get_columns("addresses")
            }
        )
        revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))

    assert tables == EXPECTED_TABLES
    assert revision == HEAD_REVISION
    assert {"first_name", "last_name", "email", "mobile_verified_at", "deleted_at"} <= users_columns
    assert "full_name" not in users_columns
    assert "deleted_at" not in addresses_columns


async def test_migration_matches_sqlalchemy_metadata(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as connection:
        differences = await connection.run_sync(
            lambda sync_connection: compare_metadata(
                MigrationContext.configure(sync_connection), Base.metadata
            )
        )

    assert differences == []


async def _role_permission_keys(session: AsyncSession) -> dict[str, set[str]]:
    rows = await session.execute(
        select(Role.name, Permission.key)
        .join(RolePermission, RolePermission.role_id == Role.id)
        .join(Permission, Permission.id == RolePermission.permission_id)
    )
    grants: dict[str, set[str]] = {}
    for role_name, key in rows:
        grants.setdefault(role_name, set()).add(key)
    return grants


async def test_rbac_seed_is_idempotent(db_session: AsyncSession) -> None:
    await seed_rbac(db_session)
    await seed_rbac(db_session)
    await db_session.flush()

    names = set((await db_session.scalars(select(Role.name))).all())
    keys = set((await db_session.scalars(select(Permission.key))).all())
    grant_count = len((await db_session.execute(select(RolePermission.role_id))).all())

    assert {role.name for role in DEFAULT_ROLES} <= names
    assert keys == {permission.key for permission in PERMISSIONS}
    assert grant_count == sum(len(granted) for granted in ROLE_PERMISSIONS.values())


async def test_rbac_seed_grants_match_mapping(db_session: AsyncSession) -> None:
    await seed_rbac(db_session)
    await db_session.flush()

    grants = await _role_permission_keys(db_session)

    assert grants["super_admin"] == set(ALL_PERMISSION_KEYS)
    assert "customer" not in grants
    assert "users:manage_roles" not in grants["admin"]
    for role_name, keys in ROLE_PERMISSIONS.items():
        assert grants.get(role_name, set()) == set(keys)


async def test_rbac_seed_never_deletes_unlisted_rows(db_session: AsyncSession) -> None:
    db_session.add(Role(name="legacy_role", description="Not in DEFAULT_ROLES"))
    db_session.add(Permission(key="legacy:action", module="legacy"))
    await db_session.flush()

    await seed_rbac(db_session)
    await db_session.flush()

    names = set((await db_session.scalars(select(Role.name))).all())
    keys = set((await db_session.scalars(select(Permission.key))).all())
    assert "legacy_role" in names
    assert "legacy:action" in keys


def _unique_phone() -> str:
    return f"+989{uuid4().int % 1_000_000_000:09d}"


async def test_unique_user_phone_and_utc_timestamps(db_session: AsyncSession) -> None:
    phone = _unique_phone()
    first_user = User(phone=phone)
    db_session.add(first_user)
    await db_session.flush()

    assert first_user.created_at.utcoffset() == timedelta(0)

    db_session.add(User(phone=phone))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_soft_deleted_user_frees_its_phone(db_session: AsyncSession) -> None:
    phone = _unique_phone()
    old_user = User(phone=phone)
    db_session.add(old_user)
    await db_session.flush()
    old_user.soft_delete()
    await db_session.flush()

    new_user = User(phone=phone)
    db_session.add(new_user)
    await db_session.flush()

    assert new_user.id != old_user.id


@pytest.mark.parametrize("phone", ["09121234567", "+98912123456", "+989121234567 ", " "])
async def test_user_phone_must_be_e164(db_session: AsyncSession, phone: str) -> None:
    db_session.add(User(phone=phone))

    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.parametrize("field", ["first_name", "last_name"])
async def test_user_names_cannot_be_blank(db_session: AsyncSession, field: str) -> None:
    db_session.add(User(phone=_unique_phone(), **{field: "   "}))

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_user_profile_fields_are_optional(db_session: AsyncSession) -> None:
    user = User(phone=_unique_phone())
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    assert (user.first_name, user.last_name, user.email, user.mobile_verified_at) == (
        None,
        None,
        None,
        None,
    )


async def test_not_deleted_excludes_soft_deleted_rows(db_session: AsyncSession) -> None:
    active_user = User(phone=_unique_phone())
    deleted_user = User(phone=_unique_phone())
    db_session.add_all([active_user, deleted_user])
    await db_session.flush()

    deleted_user.soft_delete()
    await db_session.flush()
    await db_session.refresh(deleted_user)

    ids = {active_user.id, deleted_user.id}
    visible_ids = set(
        (await db_session.scalars(select(User.id).where(User.id.in_(ids), not_deleted(User)))).all()
    )

    assert visible_ids == {active_user.id}
    assert deleted_user.deleted_at is not None
    assert deleted_user.deleted_at.utcoffset() == timedelta(0)


async def test_address_requires_an_existing_user(db_session: AsyncSession) -> None:
    db_session.add(
        Address(
            user_id=uuid4(),
            recipient_name="Test Recipient",
            phone="+989121234567",
            province="Tehran",
            city="Tehran",
            postal_code="1234567890",
            address_line="Test address",
        )
    )

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_user_can_have_only_one_default_address(db_session: AsyncSession) -> None:
    user = User(phone=_unique_phone())
    db_session.add(user)
    await db_session.flush()

    address_values = {
        "user_id": user.id,
        "recipient_name": "Test Recipient",
        "phone": "+989121234567",
        "province": "Tehran",
        "city": "Tehran",
        "postal_code": "1234567890",
        "address_line": "Test address",
        "is_default": True,
    }
    db_session.add_all([Address(**address_values), Address(**address_values)])

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_user_status_check_constraint(db_session: AsyncSession) -> None:
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text("INSERT INTO users (phone, status) VALUES (:phone, 'not-a-valid-status')"),
            {"phone": f"+989{uuid4().int % 10_000_000_000:010d}"[:13]},
        )


async def test_audit_logs_cannot_be_deleted(db_session: AsyncSession) -> None:
    audit_log = AuditLog(
        action="test.created",
        entity_type="test",
        entity_id=uuid4(),
        metadata_={"source": "integration-test"},
        ip="127.0.0.1",
    )
    db_session.add(audit_log)
    await db_session.flush()

    await db_session.delete(audit_log)
    with pytest.raises(DBAPIError):
        await db_session.flush()


async def test_readiness_and_development_database_status(
    migrated_database: str,
) -> None:
    settings = Settings(
        database_url=migrated_database,
        jwt_secret="test-secret-that-is-at-least-32-characters",
        environment=Environment.TESTING,
        cors_origins=[],
        otp_mock_enabled=True,
    )
    application = create_app(settings)

    async with application.router.lifespan_context(application):
        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            root_response = await client.get("/ready")
            versioned_response = await client.get("/api/v1/ready")
            status_response = await client.get("/api/v1/dev/database-status")

    assert root_response.status_code == 200
    assert versioned_response.status_code == 200
    assert root_response.json()["database"] == "available"
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "connected"
    assert status_response.json()["database"]
    assert status_response.json()["migration_revision"] == HEAD_REVISION


def _otp_code(**overrides: object) -> OtpCode:
    mobile = _unique_phone()
    values: dict[str, object] = {
        "mobile": mobile,
        "code_hash": hash_otp_code("123456", mobile, b"k" * 32),
        "expires_at": utc_now() + timedelta(minutes=2),
        "ip": "203.0.113.7",
    }
    return OtpCode(**{**values, **overrides})


async def test_otp_code_stores_hash_with_defaults(db_session: AsyncSession) -> None:
    otp = _otp_code()
    db_session.add(otp)
    await db_session.flush()
    await db_session.refresh(otp)

    assert otp.attempt_count == 0
    assert otp.consumed_at is None
    assert otp.expires_at.utcoffset() == timedelta(0)
    assert "123456" not in otp.code_hash


async def test_otp_codes_has_mobile_created_at_index(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as connection:
        indexes = await connection.run_sync(
            lambda sync_connection: {
                index["name"]: index["column_names"]
                for index in inspect(sync_connection).get_indexes("otp_codes")
            }
        )

    assert indexes["ix_otp_codes_mobile_created_at"] == ["mobile", "created_at"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"code_hash": "123456"},
        {"code_hash": "A" * 64},
        {"mobile": "09121234567"},
        {"attempt_count": -1},
    ],
    ids=["plaintext-code", "non-hex-hash", "non-e164-mobile", "negative-attempts"],
)
async def test_otp_code_constraints(db_session: AsyncSession, overrides: dict[str, object]) -> None:
    db_session.add(_otp_code(**overrides))

    with pytest.raises(IntegrityError):
        await db_session.flush()


WAREHOUSE_MANAGER_ID = UUID("d092d5a1-5d54-5abd-9dbc-d5921a375a2f")
PRE_ROLE_CLEANUP_REVISION = "20261006_0004"


async def _alembic(database_url: str, action: str, revision: str) -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    # env.py calls asyncio.run, which cannot run inside the test's event loop.
    await asyncio.to_thread(getattr(command, action), config, revision)


async def _warehouse_manager(db_engine: AsyncEngine) -> Role | None:
    async with AsyncSession(db_engine) as session:
        role: Role | None = await session.scalar(
            select(Role).where(Role.name == "warehouse_manager")
        )
        return role


async def test_role_cleanup_migration_removes_unreferenced_warehouse_manager(
    db_engine: AsyncEngine, migrated_database: str
) -> None:
    try:
        await _alembic(migrated_database, "downgrade", PRE_ROLE_CLEANUP_REVISION)
        assert await _warehouse_manager(db_engine) is not None

        await _alembic(migrated_database, "upgrade", "head")
        assert await _warehouse_manager(db_engine) is None

        await _alembic(migrated_database, "downgrade", PRE_ROLE_CLEANUP_REVISION)
        restored = await _warehouse_manager(db_engine)
        assert restored is not None
        assert (restored.id, restored.description, restored.is_system) == (
            WAREHOUSE_MANAGER_ID,
            "Warehouse manager",
            True,
        )
    finally:
        await _alembic(migrated_database, "upgrade", "head")
    assert await _warehouse_manager(db_engine) is None


async def test_role_cleanup_migration_keeps_referenced_warehouse_manager(
    db_engine: AsyncEngine, migrated_database: str
) -> None:
    user = User(phone="+989120000555")
    try:
        await _alembic(migrated_database, "downgrade", PRE_ROLE_CLEANUP_REVISION)
        async with AsyncSession(db_engine, expire_on_commit=False) as session, session.begin():
            session.add(user)
            await session.flush()
            session.add(UserRole(user_id=user.id, role_id=WAREHOUSE_MANAGER_ID))

        await _alembic(migrated_database, "upgrade", "head")
        kept = await _warehouse_manager(db_engine)
        assert kept is not None
        assert kept.id == WAREHOUSE_MANAGER_ID

        # Downgrade leaves the kept row (and its assignment) as it is.
        await _alembic(migrated_database, "downgrade", PRE_ROLE_CLEANUP_REVISION)
        async with AsyncSession(db_engine) as session:
            assignments = await session.scalar(
                select(func.count()).select_from(UserRole).where(UserRole.user_id == user.id)
            )
        assert assignments == 1
    finally:
        async with AsyncSession(db_engine) as session, session.begin():
            await session.execute(delete(User).where(User.phone == "+989120000555"))
        await _alembic(migrated_database, "upgrade", "head")
    # Once unreferenced, a later run of the migration removes it.
    await _alembic(migrated_database, "downgrade", PRE_ROLE_CLEANUP_REVISION)
    await _alembic(migrated_database, "upgrade", "head")
    assert await _warehouse_manager(db_engine) is None
