"""Idempotency-Key: header, request hash, replay, reuse, expiry, concurrency (ORD-02)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Annotated, Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from conftest import MakeAccount
from fastapi import APIRouter, Depends, Response
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import Settings
from app.core.errors import AppError, ConflictError
from app.core.time import utc_now
from app.db.models import IdempotencyKey
from app.db.session import get_db_session
from app.main import create_app
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.service import CurrentUser
from app.shared.idempotency import (
    IDEMPOTENCY_TTL,
    NO_STORE,
    IdempotencyService,
    idempotency_key,
    purge_expired_idempotency_keys,
    replay_response,
    request_hash,
)

URL = "/api/v1/_test/items"

# --- request hash and header (no database) -------------------------------------------


def test_hash_ignores_key_order_and_whitespace_but_not_values() -> None:
    first = request_hash(path={"id": "1"}, body={"a": 1, "b": [1, 2], "c": "سلام"})
    same = request_hash(body={"c": "سلام", "b": [1, 2], "a": 1}, path={"id": "1"})
    assert first == same and len(first) == 64
    assert request_hash(path={"id": "1"}, body={"a": 2, "b": [1, 2], "c": "سلام"}) != first
    assert request_hash(path={"id": "2"}, body={"a": 1, "b": [1, 2], "c": "سلام"}) != first
    assert request_hash(path={"id": "1"}, body={"a": 1, "b": [2, 1], "c": "سلام"}) != first


@pytest.mark.parametrize("header", [None, "", " ", "has space", "کلید", "x" * 256, "a\tb"])
def test_invalid_headers_are_400(header: str | None) -> None:
    with pytest.raises(AppError) as caught:
        idempotency_key(header)
    assert caught.value.status_code == 400
    assert caught.value.details[0]["field"] == "header.Idempotency-Key"


@pytest.mark.parametrize(
    "header", ["a", "x" * 255, "order-2026-10-18:7f3c", "6f1c2a9e-3b7d-4e21-9a55-0c8d1e2f3a4b"]
)
def test_valid_headers(header: str) -> None:
    assert idempotency_key(header) == header


# --- the service behind a test route (integration) -----------------------------------


class ItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: int


class Calls:
    """Counts real executions of the handler (the side effect a replay must skip)."""

    def __init__(self) -> None:
        self.count = 0


def _router(calls: Calls) -> APIRouter:
    router = APIRouter(prefix="/_test")

    @router.post("/items/{item}", status_code=201)
    async def create_item(
        item: str,
        payload: ItemRequest,
        response: Response,
        user: Annotated[CurrentUser, Depends(get_current_user)],
        key: Annotated[str, Depends(idempotency_key)],
        session: Annotated[AsyncSession, Depends(get_db_session)],
    ) -> Any:
        hash_ = request_hash(path={"item": item}, body=payload.model_dump(mode="json"))
        async with session.begin():
            service = IdempotencyService(session)
            stored = await service.begin(
                user_id=user.id, scope="test.items", key=key, request_hash=hash_
            )
            if stored is not None:
                return replay_response(stored)
            calls.count += 1
            # Long enough for a concurrent duplicate to queue on the key lock.
            await asyncio.sleep(0.05)
            if payload.value < 0:
                raise ConflictError(message="Rejected")
            body = {"item": item, "value": payload.value, "run": calls.count}
            await service.complete(
                user_id=user.id,
                scope="test.items",
                key=key,
                request_hash=hash_,
                status_code=201,
                body=body,
            )
        response.headers.update(NO_STORE)
        return body

    return router


@pytest_asyncio.fixture
async def calls() -> Calls:
    return Calls()


@pytest_asyncio.fixture
async def client(
    settings: Settings, db_engine: AsyncEngine, calls: Calls, make_account: MakeAccount
) -> AsyncIterator[AsyncClient]:
    # make_account is requested first so this client (and its rows) go before the users.
    database_url = db_engine.url.render_as_string(hide_password=False)
    application = create_app(settings.model_copy(update={"database_url": database_url}))
    application.include_router(_router(calls), prefix="/api/v1")
    async with application.router.lifespan_context(application):
        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
            yield test_client


async def _post(
    client: AsyncClient, headers: dict[str, str], key: str | None, value: int, item: str = "a"
) -> Any:
    sent = dict(headers)
    if key is not None:
        sent["Idempotency-Key"] = key
    return await client.post(f"{URL}/{item}", json={"value": value}, headers=sent)


async def _rows(engine: AsyncEngine, user_id: UUID) -> int:
    async with AsyncSession(engine) as session:
        count = await session.scalar(select(func.count()).where(IdempotencyKey.user_id == user_id))
        return int(count or 0)


@pytest.mark.integration
async def test_same_key_and_body_replays_the_first_response(
    client: AsyncClient, make_account: MakeAccount, calls: Calls, db_engine: AsyncEngine
) -> None:
    user = await make_account("customer")
    key = str(uuid4())

    first = await _post(client, user.headers, key, 5)
    again = await _post(client, user.headers, key, 5)

    assert (first.status_code, again.status_code) == (201, 201)
    assert first.json() == again.json() == {"item": "a", "value": 5, "run": 1}
    assert again.headers["cache-control"] == "no-store"
    assert calls.count == 1
    assert await _rows(db_engine, user.id) == 1


@pytest.mark.integration
async def test_same_key_with_another_body_or_path_is_422(
    client: AsyncClient, make_account: MakeAccount, calls: Calls
) -> None:
    user = await make_account("customer")
    key = str(uuid4())
    await _post(client, user.headers, key, 5)

    other_body = await _post(client, user.headers, key, 6)
    other_path = await _post(client, user.headers, key, 5, item="b")

    for response in (other_body, other_path):
        assert response.status_code == 422, response.text
        error = response.json()["error"]
        assert error["code"] == "IDEMPOTENCY_KEY_REUSED"
        assert error["details"][0]["field"] == "header.Idempotency-Key"
    assert calls.count == 1


@pytest.mark.integration
async def test_keys_are_per_user(
    client: AsyncClient, make_account: MakeAccount, calls: Calls
) -> None:
    first, second = await make_account("customer"), await make_account("customer")
    key = "shared-key"

    mine = await _post(client, first.headers, key, 5)
    theirs = await _post(client, second.headers, key, 7)

    assert (mine.json()["value"], theirs.json()["value"]) == (5, 7)
    assert calls.count == 2


@pytest.mark.integration
async def test_a_failed_request_stores_nothing_and_can_be_retried(
    client: AsyncClient, make_account: MakeAccount, calls: Calls, db_engine: AsyncEngine
) -> None:
    user = await make_account("customer")
    key = str(uuid4())

    failed = await _post(client, user.headers, key, -1)
    assert failed.status_code == 409
    assert await _rows(db_engine, user.id) == 0
    retried_same = await _post(client, user.headers, key, -1)
    fixed = await _post(client, user.headers, str(uuid4()), 1)

    assert retried_same.status_code == 409
    assert fixed.status_code == 201
    assert calls.count == 3


@pytest.mark.integration
async def test_concurrent_duplicates_run_once(
    client: AsyncClient, make_account: MakeAccount, calls: Calls
) -> None:
    user = await make_account("customer")
    key = str(uuid4())

    responses = await asyncio.gather(*(_post(client, user.headers, key, 9) for _ in range(3)))

    assert [response.status_code for response in responses] == [201, 201, 201]
    assert all(response.json() == responses[0].json() for response in responses)
    assert calls.count == 1


@pytest.mark.integration
async def test_missing_or_bad_header_is_400_after_authentication(
    client: AsyncClient, make_account: MakeAccount, calls: Calls
) -> None:
    unauthenticated = await _post(client, {}, None, 1)
    assert unauthenticated.status_code == 401
    user = await make_account("customer")
    for key in (None, "has space", "x" * 256):
        response = await _post(client, user.headers, key, 1)
        assert response.status_code == 400, response.text
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert calls.count == 0


# --- expiry and purge (service level) ------------------------------------------------


@pytest.mark.integration
async def test_an_expired_key_runs_again_and_purge_removes_old_keys(
    make_account: MakeAccount, db_engine: AsyncEngine
) -> None:
    user = await make_account("customer")
    now = utc_now()
    hash_ = request_hash(body={"v": 1})

    async with AsyncSession(db_engine) as session, session.begin():
        service = IdempotencyService(session)
        assert (
            await service.begin(
                user_id=user.id, scope="test.items", key="k", request_hash=hash_, now=now
            )
            is None
        )
        await service.complete(
            user_id=user.id,
            scope="test.items",
            key="k",
            request_hash=hash_,
            status_code=200,
            body={"ok": True},
            now=now,
        )

    just_before = now + IDEMPOTENCY_TTL - timedelta(seconds=1)
    at_expiry = now + IDEMPOTENCY_TTL
    async with AsyncSession(db_engine) as session, session.begin():
        service = IdempotencyService(session)
        stored = await service.begin(
            user_id=user.id, scope="test.items", key="k", request_hash=hash_, now=just_before
        )
        assert stored is not None and stored.body == {"ok": True}
        # Another scope is another key.
        assert (
            await service.begin(
                user_id=user.id, scope="test.other", key="k", request_hash=hash_, now=just_before
            )
            is None
        )
    async with AsyncSession(db_engine) as session, session.begin():
        # Expired: forgotten, even with another body.
        assert (
            await IdempotencyService(session).begin(
                user_id=user.id,
                scope="test.items",
                key="k",
                request_hash=request_hash(body={"v": 2}),
                now=at_expiry,
            )
            is None
        )
    assert await _rows(db_engine, user.id) == 0

    async with AsyncSession(db_engine) as session, session.begin():
        for key, created in (("old", now - IDEMPOTENCY_TTL * 2), ("live", now)):
            await IdempotencyService(session).complete(
                user_id=user.id,
                scope="test.items",
                key=key,
                request_hash=hash_,
                status_code=201,
                body={},
                now=created,
            )
    async with AsyncSession(db_engine) as session, session.begin():
        assert await purge_expired_idempotency_keys(session, now=now) == 1
    async with AsyncSession(db_engine) as session:
        keys = list(
            await session.scalars(
                select(IdempotencyKey.key).where(IdempotencyKey.user_id == user.id)
            )
        )
    assert keys == ["live"]
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(IdempotencyKey).where(IdempotencyKey.user_id == user.id))


@pytest.mark.integration
async def test_service_guards(db_engine: AsyncEngine, make_account: MakeAccount) -> None:
    user = await make_account("customer")
    async with AsyncSession(db_engine) as session:
        with pytest.raises(RuntimeError):
            await IdempotencyService(session).begin(
                user_id=user.id, scope="test.items", key="k", request_hash="0" * 64
            )
    async with AsyncSession(db_engine) as session, session.begin():
        with pytest.raises(ValueError):
            await IdempotencyService(session).complete(
                user_id=user.id,
                scope="test.items",
                key="k",
                request_hash="0" * 64,
                status_code=409,
                body={},
            )
        with pytest.raises(ValueError, match="mode='json'"):
            await IdempotencyService(session).complete(
                user_id=user.id,
                scope="test.items",
                key="k",
                request_hash="0" * 64,
                status_code=201,
                body={"id": uuid4()},
            )
        with pytest.raises(ValueError):
            await purge_expired_idempotency_keys(session, limit=0)
