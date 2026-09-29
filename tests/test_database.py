from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from datetime import timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from httpx import ASGITransport, AsyncClient
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from alembic import command
from app.core.config import Environment, Settings
from app.db.base import Base
from app.db.models import Address, AuditLog, Role, User
from app.db.models.common import not_deleted
from app.db.seed import DEFAULT_ROLES, seed_roles
from app.main import create_app

pytestmark = pytest.mark.integration

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


@pytest.fixture(scope="session")
def database_url() -> str:
    value = os.getenv("TEST_DATABASE_URL")
    if not value:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    # The database name itself is validated once per session in conftest.pytest_sessionstart.
    return value


@pytest.fixture(scope="session")
def migrated_database(database_url: str) -> Iterator[str]:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

    command.downgrade(config, "base")
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    yield database_url


@pytest_asyncio.fixture
async def db_engine(migrated_database: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(
        migrated_database,
        connect_args={"server_settings": {"timezone": "UTC"}},
    )
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        yield session
        await session.rollback()


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
    assert revision == "20260913_0001"
    assert "deleted_at" in users_columns
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


async def test_unique_user_phone_and_utc_timestamps(db_session: AsyncSession) -> None:
    phone = f"+989{uuid4().int % 10_000_000_000:010d}"[:13]
    first_user = User(phone=phone)
    db_session.add(first_user)
    await db_session.flush()

    assert first_user.created_at.utcoffset() == timedelta(0)

    db_session.add(User(phone=phone))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_not_deleted_excludes_soft_deleted_rows(db_session: AsyncSession) -> None:
    active_user = User(phone=f"+989{uuid4().int % 10_000_000_000:010d}"[:13])
    deleted_user = User(phone=f"+989{uuid4().int % 10_000_000_000:010d}"[:13])
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
    user = User(phone=f"+989{uuid4().int % 10_000_000_000:010d}"[:13])
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
    assert status_response.json()["migration_revision"] == "20260913_0001"
