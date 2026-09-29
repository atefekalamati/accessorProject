from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

# app.main intentionally validates required settings at import time. Tests supply
# isolated startup values before importing the application factory.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://user:password@localhost:5432/project_ak"
)
os.environ.setdefault("JWT_SECRET", "test-secret-that-is-at-least-32-characters")

from app.core.config import Environment, Settings
from app.main import create_app

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
    )


@pytest_asyncio.fixture
async def client(settings: Settings) -> AsyncIterator[AsyncClient]:
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
            yield test_client
