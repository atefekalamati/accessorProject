from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from httpx import ASGITransport, AsyncClient
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import Environment, Settings
from app.db.base import Base
from app.db.models import Address, AuditLog, Role, User
from app.db.models.common import not_deleted
from app.db.seed import DEFAULT_ROLES, seed_roles
from app.main import create_app

pytestmark = pytest.mark.integration

HEAD_REVISION = "20261006_0002"

EXPECTED_TABLES = {
    "addresses",
    "alembic_version",
    "app_settings",
    "audit_logs",
    "permissions",
    "role_permissions",
    "roles",
    "user_roles",
    "users",
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


async def test_role_seed_is_idempotent(db_session: AsyncSession) -> None:
    await seed_roles(db_session)
    await seed_roles(db_session)
    await db_session.flush()

    names = (await db_session.scalars(select(Role.name).order_by(Role.name))).all()

    assert names == sorted(role.name for role in DEFAULT_ROLES)


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
