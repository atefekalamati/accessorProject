from __future__ import annotations

import os
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from datetime import timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

# app.main intentionally validates required settings at import time. Tests supply
# isolated startup values before importing the application factory.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://user:password@localhost:5432/project_ak"
)
os.environ.setdefault("JWT_SECRET", "test-secret-that-is-at-least-32-characters")
os.environ.setdefault("OTP_HASH_SECRET", "test-otp-hash-secret-at-least-32-characters")

from alembic import command
from app.core.config import Environment, MediaStorage, Settings
from app.core.time import utc_now
from app.db.models import Category, Media, OtpCode
from app.db.seed import seed_rbac
from app.main import create_app
from app.modules.auth.otp import hash_otp_code, otp_hash_key

TEST_DATABASE_SUFFIX = "_test"
TEST_DATABASE_GUARD_EXIT_CODE = 3


def unsafe_test_database_reason(value: str | None) -> str | None:
    """Return why TEST_DATABASE_URL is unsafe, or None when it is unset or safe.

    Integration tests downgrade the whole schema, so only a database whose name
    ends with ``_test`` is accepted.
    """
    if not value:
        return None
    try:
        database_name = make_url(value).database
    except ArgumentError:
        return "TEST_DATABASE_URL is not a valid database URL"
    if database_name is None or not database_name.endswith(TEST_DATABASE_SUFFIX):
        return (
            f"TEST_DATABASE_URL must point to a database whose name ends with "
            f"'{TEST_DATABASE_SUFFIX}' (got {database_name!r})"
        )
    return None


def pytest_sessionstart(session: pytest.Session) -> None:
    error = unsafe_test_database_reason(os.getenv("TEST_DATABASE_URL"))
    if error is not None:
        pytest.exit(f"Aborting test session: {error}", returncode=TEST_DATABASE_GUARD_EXIT_CODE)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://user:password@localhost:5432/project_ak",
        jwt_secret="test-secret-that-is-at-least-32-characters",
        environment=Environment.TESTING,
        cors_origins=["http://localhost:3000"],
        otp_mock_enabled=True,
        otp_hash_secret="test-otp-hash-secret-at-least-32-characters",
        media_storage=MediaStorage.MEMORY,
        media_public_base_url="https://cdn.example.com/media",
        media_allowed_hosts=["cdn.example.com"],
    )


@pytest_asyncio.fixture
async def client(settings: Settings) -> AsyncIterator[AsyncClient]:
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
            yield test_client


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


AUTH_CLIENT_IP = "198.51.100.23"
TEST_OTP_CODE = "123456"


@pytest_asyncio.fixture
async def auth_client(settings: Settings, db_engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    """A client on the migrated test database, with RBAC roles seeded."""
    async with AsyncSession(db_engine) as session, session.begin():
        await seed_rbac(session)
    database_url = db_engine.url.render_as_string(hide_password=False)
    application = create_app(settings.model_copy(update={"database_url": database_url}))
    async with application.router.lifespan_context(application):
        transport = ASGITransport(app=application, client=(AUTH_CLIENT_IP, 50000))
        async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
            yield test_client


@pytest.fixture
def issue_otp(settings: Settings, db_engine: AsyncEngine) -> Callable[..., Awaitable[OtpCode]]:
    """Insert an OTP for ``mobile`` directly, bypassing request-otp rate limits."""

    async def _issue(
        mobile: str, code: str = TEST_OTP_CODE, *, ttl: timedelta = timedelta(minutes=2)
    ) -> OtpCode:
        now = utc_now()
        otp = OtpCode(
            mobile=mobile,
            code_hash=hash_otp_code(code, mobile, otp_hash_key(settings)),
            expires_at=now + ttl,
            created_at=now,
        )
        async with AsyncSession(db_engine, expire_on_commit=False) as session, session.begin():
            session.add(otp)
        return otp

    return _issue


MEDIA_BASE_URL = "https://cdn.example.com/media"
MakeMedia = Callable[[], Awaitable[Media]]


@pytest_asyncio.fixture
async def make_media(db_engine: AsyncEngine) -> AsyncIterator[MakeMedia]:
    """Insert media rows (no file); their public URL is MEDIA_BASE_URL/<storage_key>."""
    created: list[Media] = []

    async def _make() -> Media:
        media = Media(
            storage_key=f"{uuid4().hex}.webp",
            content_type="image/webp",
            size_bytes=1000,
            width=10,
            height=10,
        )
        async with AsyncSession(db_engine, expire_on_commit=False) as session, session.begin():
            session.add(media)
        created.append(media)
        return media

    yield _make
    ids = [media.id for media in created]
    async with AsyncSession(db_engine) as session, session.begin():
        # Categories of the test may still point at the media (FK RESTRICT).
        await session.execute(
            update(Category).where(Category.image_media_id.in_(ids)).values(image_media_id=None)
        )
        await session.execute(delete(Media).where(Media.id.in_(ids)))


def unique_mobile() -> str:
    return f"+989{uuid4().int % 1_000_000_000:09d}"


@pytest.fixture
def new_mobile() -> str:
    return unique_mobile()
