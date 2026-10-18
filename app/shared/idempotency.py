"""The ``Idempotency-Key`` header for retry-safe writes (ORD-02, D34, ADR-046).

Use inside the caller's transaction, before any other lock of the request (global lock
order, ADR-044: idempotency → cart → order advisory → inventory → code → redemption)::

    hash_ = request_hash(path={"...": ...}, body=payload.model_dump(mode="json"))
    async with session.begin():
        service = IdempotencyService(session)
        stored = await service.begin(user_id=..., scope="orders.create", key=key,
                                     request_hash=hash_)
        if stored is not None:
            return replay_response(stored)
        ...  # the real work
        await service.complete(..., status_code=201, body=response_body)

Route signature order matters: authentication (401) and the verified-mobile check come
before ``idempotency_key`` so a bad header never answers before them. Store the body as
``model_dump(mode="json")``; only the status and body replay (no other headers), always
with ``Cache-Control: no-store``.

The advisory lock serializes every request with the same (user, scope, key): a duplicate
waits until the first commits and then replays its response. If the first rolls back
(any error), nothing is stored and the duplicate runs as a fresh request.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Annotated, Any, Final
from uuid import UUID

from fastapi import Header
from fastapi.responses import JSONResponse
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BadRequestError, BusinessRuleError, ErrorCode
from app.core.time import utc_now
from app.db.models.idempotency import MAX_IDEMPOTENCY_KEY_LENGTH, IdempotencyKey

IDEMPOTENCY_TTL: Final = timedelta(hours=24)
_KEY: Final = re.compile(rf"[!-~]{{1,{MAX_IDEMPOTENCY_KEY_LENGTH}}}")
NO_STORE: Final = {"Cache-Control": "no-store"}


def _invalid_key(message: str) -> BadRequestError:
    return BadRequestError(
        message="Request validation failed",
        details=[{"field": "header.Idempotency-Key", "message": message, "type": "value_error"}],
    )


def idempotency_key(
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str:
    """The required header: 1..255 printable ASCII characters without spaces; else 400."""
    if idempotency_key is None or idempotency_key == "":
        raise _invalid_key("Required")
    if not _KEY.fullmatch(idempotency_key):
        raise _invalid_key(
            f"1 to {MAX_IDEMPOTENCY_KEY_LENGTH} printable ASCII characters, no spaces"
        )
    return idempotency_key


def request_hash(*, path: dict[str, Any] | None = None, body: Any = None) -> str:
    """SHA-256 of the canonical JSON of the path parameters and the parsed body.

    Key order and whitespace never change the hash; any value change does.
    """
    canonical = json.dumps(
        {"path": path or {}, "body": body},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class StoredResponse:
    status_code: int
    body: Any


def replay_response(stored: StoredResponse) -> JSONResponse:
    """The original response again; never cached (it may hold the user's address)."""
    return JSONResponse(status_code=stored.status_code, content=stored.body, headers=dict(NO_STORE))


def _reused() -> BusinessRuleError:
    return BusinessRuleError(
        code=ErrorCode.IDEMPOTENCY_KEY_REUSED,
        message="This Idempotency-Key was used with a different request",
        details=[{"field": "header.Idempotency-Key", "type": "reused_with_different_body"}],
    )


class IdempotencyService:
    """Runs in the caller's transaction and never commits."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def begin(
        self,
        *,
        user_id: UUID,
        scope: str,
        key: str,
        request_hash: str,
        now: datetime | None = None,
    ) -> StoredResponse | None:
        """Lock the key; the stored response to replay, or None to run the request.

        A different request under a live key is 422; an expired key is forgotten.
        """
        if not self._session.in_transaction():
            raise RuntimeError("IdempotencyService needs the caller's transaction")
        # A hash collision between two keys only makes one wait for the other.
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock, 0))"),
            {"lock": f"idem:{scope}:{user_id}:{key}"},
        )
        now = now or utc_now()
        stored = (
            await self._session.scalars(
                select(IdempotencyKey).where(
                    IdempotencyKey.user_id == user_id,
                    IdempotencyKey.scope == scope,
                    IdempotencyKey.key == key,
                )
            )
        ).one_or_none()
        if stored is None:
            return None
        if stored.expires_at <= now:
            await self._session.delete(stored)
            await self._session.flush()
            return None
        if stored.request_hash != request_hash:
            raise _reused()
        return StoredResponse(status_code=stored.response_status, body=stored.response_body)

    async def complete(
        self,
        *,
        user_id: UUID,
        scope: str,
        key: str,
        request_hash: str,
        status_code: int,
        body: Any,
        now: datetime | None = None,
    ) -> None:
        """Store a successful response; it commits or rolls back with the request."""
        if not 200 <= status_code <= 299:
            raise ValueError("only successful responses are stored")
        try:
            json.dumps(body)
        except (TypeError, ValueError) as error:
            raise ValueError("store the body as model_dump(mode='json')") from error
        now = now or utc_now()
        self._session.add(
            IdempotencyKey(
                user_id=user_id,
                scope=scope,
                key=key,
                request_hash=request_hash,
                response_status=status_code,
                response_body=body,
                created_at=now,
                expires_at=now + IDEMPOTENCY_TTL,
            )
        )
        await self._session.flush()


async def purge_expired_idempotency_keys(
    session: AsyncSession, *, now: datetime | None = None, limit: int = 1000
) -> int:
    """Delete up to ``limit`` expired keys (housekeeping; correctness never needs it)."""
    if limit < 1:
        raise ValueError("limit must be positive")
    now = now or utc_now()
    expired = (
        select(IdempotencyKey.id)
        .where(IdempotencyKey.expires_at <= now)
        .order_by(IdempotencyKey.expires_at)
        .limit(limit)
    )
    result = await session.execute(delete(IdempotencyKey).where(IdempotencyKey.id.in_(expired)))
    return int(result.rowcount or 0)  # type: ignore[attr-defined]
