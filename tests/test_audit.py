from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from starlette.requests import Request

from app.core.redaction import REDACTED, mask_email
from app.db.models import AuditLog, User
from app.shared.audit import ACTOR_SYSTEM, ACTOR_USER, build_diff, record_audit

REQUEST_ID = "3f1c2b8e-8f6a-4b8e-9a51-0c6d4f1e2a77"


class _Status(StrEnum):
    ACTIVE = "active"


def _request(client_host: str = "203.0.113.7", request_id: str | None = REQUEST_ID) -> Request:
    request = Request({"type": "http", "headers": [], "client": (client_host, 5000)})
    if request_id is not None:
        request.state.request_id = request_id
    return request


class _FakeSession:
    def __init__(self) -> None:
        self.added: list[Any] = []
        self.flushed = False

    def add(self, instance: Any) -> None:
        self.added.append(instance)

    async def flush(self) -> None:
        self.flushed = True


async def _record(session: Any = None, **overrides: Any) -> AuditLog:
    arguments: dict[str, Any] = {
        "actor_id": uuid4(),
        "action": "product.price_changed",
        "entity_type": "product",
        "entity_id": uuid4(),
        "before": {"price": 1000},
        "after": {"price": 1200},
        "request": _request(),
    }
    arguments.update(overrides)
    target = cast(AsyncSession, session or _FakeSession())
    return await record_audit(target, **arguments)


def test_diff_keeps_only_changed_fields() -> None:
    diff = build_diff({"price": 1000, "title": "Ring"}, {"price": 1200, "title": "Ring"})

    assert diff == {"price": {"before": 1000, "after": 1200, "changed": True}}


def test_diff_for_create_and_delete_covers_every_field() -> None:
    assert build_diff(None, {"price": 1000}) == {
        "price": {"before": None, "after": 1000, "changed": True}
    }
    assert build_diff({"price": 1000}, None) == {
        "price": {"before": 1000, "after": None, "changed": True}
    }


def test_diff_serializes_non_json_values() -> None:
    entity_id = UUID("00000000-0000-0000-0000-000000000001")
    at = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)

    diff = build_diff(
        None,
        {"id": entity_id, "at": at, "rate": Decimal("0.10"), "status": _Status.ACTIVE},
    )

    assert diff == {
        "at": {"before": None, "after": "2026-09-29T12:00:00+00:00", "changed": True},
        "id": {"before": None, "after": str(entity_id), "changed": True},
        "rate": {"before": None, "after": "0.10", "changed": True},
        "status": {"before": None, "after": "active", "changed": True},
    }


def test_diff_rejects_unknown_types() -> None:
    with pytest.raises(TypeError):
        build_diff(None, {"value": object()})


async def test_record_audit_adds_and_flushes_without_commit() -> None:
    session = _FakeSession()

    audit_log = await _record(session)

    assert session.added == [audit_log]
    assert session.flushed is True


async def test_record_audit_stores_request_context_and_diff() -> None:
    actor_id = uuid4()

    audit_log = await _record(actor_id=actor_id)

    assert audit_log.actor_user_id == actor_id
    assert audit_log.ip == "203.0.113.7"
    assert audit_log.metadata_ == {
        "actor": ACTOR_USER,
        "request_id": REQUEST_ID,
        "diff": {"price": {"before": 1000, "after": 1200, "changed": True}},
    }


async def test_record_audit_marks_missing_actor_as_system() -> None:
    audit_log = await _record(actor_id=None, request=None)

    assert audit_log.actor_user_id is None
    assert audit_log.ip is None
    assert audit_log.metadata_["actor"] == ACTOR_SYSTEM
    assert audit_log.metadata_["request_id"] is None


async def test_record_audit_ignores_non_ip_client_and_missing_request_id() -> None:
    audit_log = await _record(request=_request(client_host="testclient", request_id=None))

    assert audit_log.ip is None
    assert audit_log.metadata_["request_id"] is None


async def test_record_audit_redacts_secrets_and_phones() -> None:
    audit_log = await _record(
        action="user.updated",
        entity_type="user",
        before={
            "phone": "+989121234567",
            "refresh_token": "tok-old",
            "code_hash": "hash-old",
            "otp": "123456",
        },
        after={
            "phone": "+989351234567",
            "refresh_token": "tok-new",
            "code_hash": "hash-new",
            "otp": "654321",
        },
    )

    diff = audit_log.metadata_["diff"]
    assert diff["phone"] == {"before": "+98912***4567", "after": "+98935***4567", "changed": True}
    for key in ("refresh_token", "code_hash", "otp"):
        assert diff[key] == REDACTED
    for secret in ("tok-", "hash-", "123456", "654321", "1234567"):
        assert secret not in str(audit_log.metadata_)


async def test_change_stays_marked_when_masked_values_are_equal() -> None:
    audit_log = await _record(
        before={"phone": "+989121234567", "email": "ali@example.com", "name": "Ali"},
        after={"phone": "+989121114567", "email": "amir.ali@example.com", "name": "Ali"},
        field_masks={"email": mask_email},
    )

    diff = audit_log.metadata_["diff"]
    assert diff == {
        "email": {"before": "a***i@example.com", "after": "a***i@example.com", "changed": True},
        "phone": {"before": "+98912***4567", "after": "+98912***4567", "changed": True},
    }
    assert "amir" not in str(audit_log.metadata_)


async def test_field_masks_skip_missing_fields_and_null_values() -> None:
    audit_log = await _record(
        before={"email": None},
        after={"email": "ali@example.com"},
        field_masks={"email": mask_email, "absent": mask_email},
    )

    assert audit_log.metadata_["diff"] == {
        "email": {"before": None, "after": "a***i@example.com", "changed": True},
    }


@pytest.mark.parametrize(
    "action",
    ["price_changed", "Product.price_changed", "product.", ".changed", "product.price.changed"],
)
async def test_record_audit_rejects_invalid_action_name(action: str) -> None:
    session = _FakeSession()

    with pytest.raises(ValueError):
        await _record(session, action=action)
    assert session.added == []


@pytest.mark.integration
async def test_record_audit_persists_in_callers_transaction(db_session: AsyncSession) -> None:
    user = User(phone="+989121234567")
    db_session.add(user)
    await db_session.flush()

    audit_log = await _record(db_session, actor_id=user.id)

    stored = await db_session.scalar(select(AuditLog).where(AuditLog.id == audit_log.id))
    assert stored is not None
    assert stored.actor_user_id == user.id
    assert str(stored.ip) == "203.0.113.7"
    assert stored.metadata_["request_id"] == REQUEST_ID
    assert stored.metadata_["diff"] == {"price": {"before": 1000, "after": 1200, "changed": True}}


@pytest.mark.integration
async def test_rollback_discards_audit_record(db_engine: AsyncEngine) -> None:
    entity_id = uuid4()

    async with AsyncSession(db_engine) as session:
        await _record(session, actor_id=None, entity_id=entity_id)
        await session.rollback()

    async with AsyncSession(db_engine) as session:
        count = await session.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == entity_id)
        )
    assert count == 0
