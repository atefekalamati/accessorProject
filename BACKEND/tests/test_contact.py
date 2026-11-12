"""Contact form: submission, rate limits, admin queue, transitions, audit, PII (CNT-06)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from conftest import AUTH_CLIENT_IP, MakeAccount, unique_mobile
from httpx import AsyncClient, Response
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import Settings
from app.core.errors import RateLimitedError
from app.core.time import utc_now
from app.db.models import AuditLog, ContactMessage
from app.modules.content.contact import ContactService
from app.modules.content.schemas import ContactRequest

pytestmark = pytest.mark.integration

PUBLIC_URL = "/api/v1/contact"
URL = "/api/v1/admin/contact-messages"
SECRET_TEXT = "my private question about order"
NAME = "Sara Example"


@pytest_asyncio.fixture(autouse=True)
async def _cleanup(db_engine: AsyncEngine) -> AsyncIterator[None]:
    """Every message counts towards the shared test client IP, so none may survive a test."""
    yield
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(ContactMessage))


def _body(**fields: Any) -> dict[str, Any]:
    defaults = {"name": NAME, "mobile": unique_mobile(), "subject": "Hello", "message": SECRET_TEXT}
    return defaults | fields


def _error(response: Response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code


async def _rows(engine: AsyncEngine) -> list[ContactMessage]:
    async with AsyncSession(engine) as session:
        return list(await session.scalars(select(ContactMessage)))


async def _submit_and_get_id(client: AsyncClient, engine: AsyncEngine) -> str:
    response = await client.post(PUBLIC_URL, json=_body())
    assert response.status_code == 201, response.text
    rows = await _rows(engine)
    return str(max(rows, key=lambda row: row.created_at).id)


# --- submission ---------------------------------------------------------------------------


async def test_guest_message_is_stored_normalized_and_returns_nothing(
    auth_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    response = await auth_client.post(
        PUBLIC_URL,
        json=_body(name="  Sara  ", mobile="0912 345 6789", email=" A@Example.COM "),
    )

    assert response.status_code == 201, response.text
    assert response.content == b""
    [row] = await _rows(db_engine)
    assert (row.name, row.phone, row.email) == ("Sara", "+989123456789", "a@example.com")
    assert (row.status, row.user_id, str(row.ip)) == ("new", None, AUTH_CLIENT_IP)


async def test_logged_in_user_is_recorded_and_system_fields_are_ignored(
    auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
) -> None:
    customer = await make_account("customer")
    forged = str(uuid4())

    response = await auth_client.post(
        PUBLIC_URL,
        json=_body(
            status="closed", user_id=forged, ip="8.8.8.8", handled_by=forged, internal_note="x"
        ),
        headers=customer.headers,
    )

    assert response.status_code == 201, response.text
    [row] = await _rows(db_engine)
    assert row.user_id == customer.id
    assert (row.status, row.handled_by, row.internal_note) == ("new", None, None)
    assert str(row.ip) == AUTH_CLIENT_IP


async def test_a_bad_token_never_falls_back_to_guest(auth_client: AsyncClient) -> None:
    response = await auth_client.post(
        PUBLIC_URL, json=_body(), headers={"Authorization": "Bearer nope"}
    )

    _error(response, 401, "UNAUTHORIZED")


@pytest.mark.parametrize(
    "fields",
    [
        {"mobile": "12345"},
        {"name": "   "},
        {"name": "a\x00b"},
        {"subject": ""},
        {"message": ""},
        {"message": "x" * 2001},
        {"email": "not-an-email"},
        {"unknown": 1},
    ],
)
async def test_invalid_submission_is_400_and_stores_nothing(
    auth_client: AsyncClient, db_engine: AsyncEngine, fields: dict[str, Any]
) -> None:
    _error(await auth_client.post(PUBLIC_URL, json=_body(**fields)), 400, "VALIDATION_ERROR")

    assert await _rows(db_engine) == []


# --- rate limits ---------------------------------------------------------------------------


async def test_ip_cap_is_429_with_retry_after(auth_client: AsyncClient) -> None:
    for _ in range(5):
        assert (await auth_client.post(PUBLIC_URL, json=_body())).status_code == 201

    response = await auth_client.post(PUBLIC_URL, json=_body())

    _error(response, 429, "RATE_LIMITED")
    assert 3500 < int(response.headers["retry-after"]) <= 3600
    assert response.json()["error"]["details"] == [{"type": "too_many_messages_ip"}]


async def test_phone_cap_is_429_and_counts_every_spelling_of_the_number(
    auth_client: AsyncClient,
) -> None:
    mobile = unique_mobile()
    local = "0" + mobile.removeprefix("+98")
    for spelling in (mobile, local, mobile):
        assert (await auth_client.post(PUBLIC_URL, json=_body(mobile=spelling))).status_code == 201

    response = await auth_client.post(PUBLIC_URL, json=_body(mobile=local))

    _error(response, 429, "RATE_LIMITED")
    assert response.json()["error"]["details"] == [{"type": "too_many_messages_phone"}]


async def test_messages_outside_the_window_do_not_count(
    auth_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    mobile = unique_mobile()
    for _ in range(3):
        assert (await auth_client.post(PUBLIC_URL, json=_body(mobile=mobile))).status_code == 201
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            update(ContactMessage).values(created_at=utc_now() - timedelta(hours=1, seconds=1))
        )

    assert (await auth_client.post(PUBLIC_URL, json=_body(mobile=mobile))).status_code == 201


async def test_the_cap_is_exact_under_concurrent_requests(
    auth_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    mobile = unique_mobile()

    responses = await asyncio.gather(
        *(auth_client.post(PUBLIC_URL, json=_body(mobile=mobile)) for _ in range(8))
    )

    assert sorted(response.status_code for response in responses) == [201] * 3 + [429] * 5
    assert len(await _rows(db_engine)) == 3


async def test_the_caps_are_configurable(db_engine: AsyncEngine, settings: Settings) -> None:
    tight = settings.model_copy(update={"contact_max_per_phone": 1})
    payload = ContactRequest.model_validate(_body())

    async with AsyncSession(db_engine) as session:
        await ContactService(session, tight).submit(payload, user_id=None, ip="203.0.113.9")
    async with AsyncSession(db_engine) as session:
        with pytest.raises(RateLimitedError):
            await ContactService(session, tight).submit(payload, user_id=None, ip="203.0.113.10")


# --- admin queue ---------------------------------------------------------------------------


async def test_detail_shows_the_message_but_never_the_ip(
    auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
) -> None:
    support = await make_account("support")
    message_id = await _submit_and_get_id(auth_client, db_engine)

    response = await auth_client.get(f"{URL}/{message_id}", headers=support.headers)

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["message"] == SECRET_TEXT
    assert body["mobile"].startswith("+989")
    assert "ip" not in body
    assert "phone" not in body


async def test_list_is_newest_first_filtered_and_has_no_message_text(
    auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
) -> None:
    support = await make_account("support")
    first = await _submit_and_get_id(auth_client, db_engine)
    second = await _submit_and_get_id(auth_client, db_engine)
    moved = await auth_client.patch(
        f"{URL}/{first}", json={"status": "in_progress"}, headers=support.headers
    )
    assert moved.status_code == 200, moved.text

    everything = await auth_client.get(URL, headers=support.headers)
    fresh = await auth_client.get(URL, params={"status": "new"}, headers=support.headers)

    assert [item["id"] for item in everything.json()["items"]] == [second, first]
    assert [item["id"] for item in fresh.json()["items"]] == [second]
    assert "message" not in everything.json()["items"][0]
    bad = await auth_client.get(URL, params={"status": "nope"}, headers=support.headers)
    _error(bad, 400, "VALIDATION_ERROR")


@pytest.mark.parametrize(
    ("path", "target"),
    [
        ([], "closed"),
        (["in_progress"], "new"),
        (["in_progress", "closed"], "in_progress"),
        (["in_progress", "closed"], "new"),
    ],
)
async def test_invalid_transition_is_422(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    db_engine: AsyncEngine,
    path: list[str],
    target: str,
) -> None:
    support = await make_account("support")
    message_id = await _submit_and_get_id(auth_client, db_engine)
    for step in path:
        moved = await auth_client.patch(
            f"{URL}/{message_id}", json={"status": step}, headers=support.headers
        )
        assert moved.status_code == 200, moved.text

    response = await auth_client.patch(
        f"{URL}/{message_id}", json={"status": target}, headers=support.headers
    )

    _error(response, 422, "INVALID_STATE_TRANSITION")


async def test_status_change_is_audited_without_the_message_text(
    auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
) -> None:
    support = await make_account("support")
    message_id = await _submit_and_get_id(auth_client, db_engine)

    response = await auth_client.patch(
        f"{URL}/{message_id}",
        json={"status": "in_progress", "internal_note": "called back about the question"},
        headers=support.headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "in_progress"
    assert body["internal_note"] == "called back about the question"
    assert body["handled_by"] == str(support.id)
    async with AsyncSession(db_engine) as session:
        audit = (
            await session.scalars(select(AuditLog).where(AuditLog.entity_id == message_id))
        ).one()
    assert audit.action == "contact_message.updated"
    assert audit.metadata_["diff"]["status"]["after"] == "in_progress"
    assert audit.metadata_["diff"]["internal_note_changed"]["after"] is True
    stored = str(audit.metadata_)
    assert SECRET_TEXT not in stored and "called back" not in stored


async def test_same_status_and_same_note_change_nothing(
    auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
) -> None:
    support = await make_account("support")
    message_id = await _submit_and_get_id(auth_client, db_engine)

    response = await auth_client.patch(
        f"{URL}/{message_id}",
        json={"status": "new", "internal_note": None},
        headers=support.headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["handled_by"] is None
    async with AsyncSession(db_engine) as session:
        count = await session.scalars(select(AuditLog).where(AuditLog.entity_id == message_id))
        assert list(count) == []


async def test_note_can_be_cleared(
    auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
) -> None:
    support = await make_account("support")
    message_id = await _submit_and_get_id(auth_client, db_engine)
    url = f"{URL}/{message_id}"
    await auth_client.patch(url, json={"internal_note": "note"}, headers=support.headers)

    response = await auth_client.patch(url, json={"internal_note": None}, headers=support.headers)

    assert response.json()["internal_note"] is None


@pytest.mark.parametrize("body", [{}, {"status": None}, {"status": "nope"}, {"internal_note": ""}])
async def test_invalid_patch_is_400(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    db_engine: AsyncEngine,
    body: dict[str, Any],
) -> None:
    support = await make_account("support")
    message_id = await _submit_and_get_id(auth_client, db_engine)

    response = await auth_client.patch(f"{URL}/{message_id}", json=body, headers=support.headers)

    _error(response, 400, "VALIDATION_ERROR")


async def test_unknown_message_is_404(auth_client: AsyncClient, make_account: MakeAccount) -> None:
    support = await make_account("support")

    _error(await auth_client.get(f"{URL}/{uuid4()}", headers=support.headers), 404, "NOT_FOUND")
    _error(
        await auth_client.patch(
            f"{URL}/{uuid4()}", json={"status": "in_progress"}, headers=support.headers
        ),
        404,
        "NOT_FOUND",
    )


@pytest.mark.parametrize("role", ["content_manager", "customer"])
async def test_other_roles_are_403(
    auth_client: AsyncClient, make_account: MakeAccount, role: str
) -> None:
    account = await make_account(role)

    _error(await auth_client.get(URL, headers=account.headers), 403, "FORBIDDEN")


@pytest.mark.parametrize("role", ["support", "admin", "super_admin"])
async def test_handling_roles_can_read(
    auth_client: AsyncClient, make_account: MakeAccount, role: str
) -> None:
    account = await make_account(role)

    assert (await auth_client.get(URL, headers=account.headers)).status_code == 200


async def test_anonymous_admin_is_401(auth_client: AsyncClient) -> None:
    _error(await auth_client.get(URL), 401, "UNAUTHORIZED")


async def test_logs_hold_no_personal_data(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    db_engine: AsyncEngine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    support = await make_account("support")
    mobile = unique_mobile()
    caplog.set_level(logging.DEBUG)

    await auth_client.post(PUBLIC_URL, json=_body(mobile=mobile, email="sara@example.com"))
    await auth_client.post(PUBLIC_URL, json=_body(mobile=mobile, subject=""))
    [row] = await _rows(db_engine)
    await auth_client.get(f"{URL}/{row.id}", headers=support.headers)

    for secret in (SECRET_TEXT, NAME, mobile, "sara@example.com"):
        assert secret not in caplog.text
