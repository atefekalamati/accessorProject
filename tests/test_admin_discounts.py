"""Admin discount codes: CRUD, validation, audit, counts (DSC-04, ADR-044)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from conftest import MakeAccount, count_queries
from httpx import AsyncClient, Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.time import utc_now
from app.db.models import AuditLog, DiscountCode, DiscountRedemption

pytestmark = pytest.mark.integration

URL = "/api/v1/admin/discounts"


def _error(response: Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body: dict[str, Any] = response.json()["error"]
    assert body["code"] == code
    return body


def _text() -> str:
    return f"T{uuid4().hex[:10].upper()}"


@pytest_asyncio.fixture(autouse=True)
async def _cleanup(db_engine: AsyncEngine) -> AsyncIterator[None]:
    started = utc_now()
    yield
    async with AsyncSession(db_engine) as session, session.begin():
        ids = select(DiscountCode.id).where(DiscountCode.created_at >= started)
        await session.execute(
            delete(DiscountRedemption).where(DiscountRedemption.discount_code_id.in_(ids))
        )
        await session.execute(delete(DiscountCode).where(DiscountCode.created_at >= started))


async def _create(client: AsyncClient, headers: dict[str, str], **fields: Any) -> dict[str, Any]:
    body = {"code": _text(), "type": "percent", "value": 1_000} | fields
    response = await client.post(URL, json=body, headers=headers)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


async def _actions(engine: AsyncEngine, code_id: str) -> list[str]:
    async with AsyncSession(engine) as session:
        statement = (
            select(AuditLog.action)
            .where(AuditLog.entity_id == code_id)
            .order_by(AuditLog.created_at)
        )
        return list(await session.scalars(statement))


async def _redeem(engine: AsyncEngine, code_id: str, status: str = "pending") -> None:
    now = utc_now()
    async with AsyncSession(engine) as session, session.begin():
        code = await session.get(DiscountCode, UUID(code_id))
        assert code is not None
        session.add(
            DiscountRedemption(
                discount_code_id=code.id,
                order_id=uuid4(),
                phone="+989120000000",
                code=code.code,
                amount=1,
                status=status,
                confirmed_at=now if status in ("confirmed", "released") else None,
                released_at=now if status == "released" else None,
            )
        )


# --- create --------------------------------------------------------------------------


async def test_create_normalizes_ignores_system_fields_and_audits(
    auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
) -> None:
    admin = await make_account("admin")
    text = _text()

    response = await auth_client.post(
        URL,
        json={
            "code": f"  {text.lower()} ",
            "type": "percent",
            "value": 1_500,
            "max_amount": 50_000,
            "usage_limit_total": 100,
            "usage_limit_per_user": 1,
            # Server-owned fields are ignored.
            "id": str(uuid4()),
            "pending_count": 9,
            "created_by": str(uuid4()),
        },
        headers=admin.headers,
    )

    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert (body["code"], body["value"], body["max_amount"], body["is_active"]) == (
        text,
        1_500,
        50_000,
        True,
    )
    assert (body["pending_count"], body["created_by"]) == (0, str(admin.id))
    assert await _actions(db_engine, body["id"]) == ["discount.created"]


@pytest.mark.parametrize(
    "fields",
    [
        {"code": "ab"},
        {"code": "has space"},
        {"value": 0},
        {"value": 10_001},
        {"value": 10.5},
        {"value": "100"},
        {"type": "fixed", "value": 5_000, "max_amount": 1_000},
        {"type": "bogo"},
        {"starts_at": "2030-01-02T00:00:00Z", "ends_at": "2030-01-01T00:00:00Z"},
        {"starts_at": "2030-01-01T00:00:00"},
        {"usage_limit_total": 2, "usage_limit_per_user": 3},
        {"usage_limit_total": 0},
        {"min_order_amount": 0},
        {"is_active": "yes"},
        {"colour": "red"},
    ],
)
async def test_create_rejects_invalid_bodies(
    auth_client: AsyncClient, make_account: MakeAccount, fields: dict[str, Any]
) -> None:
    admin = await make_account("admin")
    body = {"code": _text(), "type": "percent", "value": 1_000} | fields

    response = await auth_client.post(URL, json=body, headers=admin.headers)

    _error(response, 400, "VALIDATION_ERROR")


async def test_duplicate_live_code_is_409_and_a_deleted_text_is_reusable(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    admin = await make_account("admin")
    first = await _create(auth_client, admin.headers)

    again = await auth_client.post(
        URL,
        json={"code": first["code"].lower(), "type": "fixed", "value": 1},
        headers=admin.headers,
    )
    _error(again, 409, "CONFLICT")

    deleted = await auth_client.delete(f"{URL}/{first['id']}", headers=admin.headers)
    assert deleted.status_code == 204
    recreated = await _create(auth_client, admin.headers, code=first["code"])
    assert recreated["id"] != first["id"] and recreated["pending_count"] == 0


# --- read ----------------------------------------------------------------------------


async def test_list_filters_states_counts_and_hides_deleted(
    auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
) -> None:
    admin = await make_account("admin")
    now = utc_now()
    prefix = f"Q{uuid4().hex[:6].upper()}"
    active = await _create(auth_client, admin.headers, code=f"{prefix}_A")
    scheduled = await _create(
        auth_client, admin.headers, code=f"{prefix}_S", starts_at=(now + timedelta(1)).isoformat()
    )
    expired = await _create(
        auth_client,
        admin.headers,
        code=f"{prefix}_E",
        starts_at=(now - timedelta(9)).isoformat(),
        ends_at=(now - timedelta(1)).isoformat(),
    )
    inactive = await _create(auth_client, admin.headers, code=f"{prefix}_I", is_active=False)
    gone = await _create(auth_client, admin.headers, code=f"{prefix}_D")
    await auth_client.delete(f"{URL}/{gone['id']}", headers=admin.headers)
    for status in ("pending", "confirmed", "released", "pending"):
        await _redeem(db_engine, active["id"], status)

    everything = await auth_client.get(
        URL, params={"q": prefix, "sort": "code"}, headers=admin.headers
    )

    assert everything.status_code == 200, everything.text
    assert everything.headers["cache-control"] == "no-store"
    rows = everything.json()["items"]
    assert [row["code"] for row in rows] == sorted(
        row["code"] for row in (active, scheduled, expired, inactive)
    )
    [counted] = [row for row in rows if row["id"] == active["id"]]
    assert (counted["pending_count"], counted["confirmed_count"], counted["released_count"]) == (
        2,
        1,
        1,
    )
    for state, expected in (
        ("active", active),
        ("scheduled", scheduled),
        ("expired", expired),
        ("inactive", inactive),
    ):
        filtered = await auth_client.get(
            URL, params={"q": prefix, "state": state}, headers=admin.headers
        )
        assert [row["id"] for row in filtered.json()["items"]] == [expected["id"]], state
    # "_" in q matches literally, not any character.
    literal = await auth_client.get(URL, params={"q": f"{prefix}_A"}, headers=admin.headers)
    assert [row["id"] for row in literal.json()["items"]] == [active["id"]]


async def test_list_has_no_n_plus_one(auth_client: AsyncClient, make_account: MakeAccount) -> None:
    admin = await make_account("admin")
    prefix = f"N{uuid4().hex[:6].upper()}"
    await _create(auth_client, admin.headers, code=f"{prefix}1")
    with count_queries(auth_client) as one:
        await auth_client.get(URL, params={"q": prefix}, headers=admin.headers)
    for index in range(2, 5):
        await _create(auth_client, admin.headers, code=f"{prefix}{index}")
    with count_queries(auth_client) as four:
        response = await auth_client.get(URL, params={"q": prefix}, headers=admin.headers)
    assert response.json()["total"] == 4
    assert len(four) == len(one)


async def test_detail_and_delete(
    auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
) -> None:
    admin = await make_account("admin")
    code = await _create(auth_client, admin.headers)

    detail = await auth_client.get(f"{URL}/{code['id']}", headers=admin.headers)
    first = await auth_client.delete(f"{URL}/{code['id']}", headers=admin.headers)
    second = await auth_client.delete(f"{URL}/{code['id']}", headers=admin.headers)

    assert detail.status_code == 200 and detail.json()["code"] == code["code"]
    assert first.status_code == 204 and first.headers["cache-control"] == "no-store"
    _error(second, 404, "NOT_FOUND")
    _error(await auth_client.get(f"{URL}/{code['id']}", headers=admin.headers), 404, "NOT_FOUND")
    _error(await auth_client.get(f"{URL}/{uuid4()}", headers=admin.headers), 404, "NOT_FOUND")
    _error(
        await auth_client.get(f"{URL}/not-a-uuid", headers=admin.headers), 400, "VALIDATION_ERROR"
    )
    assert await _actions(db_engine, code["id"]) == ["discount.created", "discount.deleted"]


# --- update --------------------------------------------------------------------------


async def test_update_audits_only_changes(
    auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
) -> None:
    admin = await make_account("admin")
    code = await _create(auth_client, admin.headers, max_amount=10_000)
    url = f"{URL}/{code['id']}"

    changed = await auth_client.patch(
        url,
        json={"value": 2_000, "max_amount": None, "code": code["code"], "type": "percent"},
        headers=admin.headers,
    )
    unchanged = await auth_client.patch(url, json={"value": 2_000}, headers=admin.headers)

    assert changed.status_code == 200, changed.text
    assert (changed.json()["value"], changed.json()["max_amount"]) == (2_000, None)
    assert unchanged.status_code == 200
    assert await _actions(db_engine, code["id"]) == ["discount.created", "discount.updated"]
    async with AsyncSession(db_engine) as session:
        [audit] = await session.scalars(
            select(AuditLog).where(
                AuditLog.entity_id == code["id"], AuditLog.action == "discount.updated"
            )
        )
    assert audit.metadata_["diff"] == {
        "value": {"before": 1_000, "after": 2_000, "changed": True},
        "max_amount": {"before": 10_000, "after": None, "changed": True},
    }


async def test_update_errors(
    auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
) -> None:
    admin = await make_account("admin")
    now = utc_now()
    fixed = await _create(auth_client, admin.headers, type="fixed", value=5_000)
    windowed = await _create(
        auth_client,
        admin.headers,
        starts_at=(now + timedelta(1)).isoformat(),
        usage_limit_total=5,
    )
    for body in (
        {},
        {"code": "OTHER-CODE"},
        {"type": "percent"},
        {"is_active": None},
        {"value": None},
        {"value": 0},
        {"unknown": 1},
    ):
        response = await auth_client.patch(f"{URL}/{fixed['id']}", json=body, headers=admin.headers)
        _error(response, 400, "VALIDATION_ERROR")
    for url, body in (
        (f"{URL}/{fixed['id']}", {"max_amount": 1_000}),
        (f"{URL}/{windowed['id']}", {"ends_at": now.isoformat()}),
        (f"{URL}/{windowed['id']}", {"usage_limit_per_user": 6}),
        (f"{URL}/{windowed['id']}", {"value": 10_001}),
    ):
        _error(
            await auth_client.patch(url, json=body, headers=admin.headers),
            422,
            "BUSINESS_RULE_VIOLATION",
        )
    _error(
        await auth_client.patch(f"{URL}/{uuid4()}", json={"value": 5}, headers=admin.headers),
        404,
        "NOT_FOUND",
    )
    # Lowering a limit below the current count is allowed (only later uses are blocked).
    for _ in range(3):
        await _redeem(db_engine, windowed["id"])
    lowered = await auth_client.patch(
        f"{URL}/{windowed['id']}", json={"usage_limit_total": 1}, headers=admin.headers
    )
    assert lowered.status_code == 200 and lowered.json()["pending_count"] == 3


# --- authorization -------------------------------------------------------------------


async def test_every_endpoint_needs_discounts_manage_before_validation(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    target = f"{URL}/{uuid4()}"
    calls: list[tuple[str, str, Any]] = [
        ("GET", URL, None),
        ("GET", target, None),
        ("POST", URL, {"code": 1}),
        ("PATCH", target, {"value": "x"}),
        ("DELETE", target, None),
    ]

    async def call(method: str, url: str, body: Any, headers: dict[str, str]) -> Response:
        return await auth_client.request(method, url, json=body, headers=headers)

    for method, url, body in calls:
        _error(await call(method, url, body, {}), 401, "UNAUTHORIZED")
    for role in ("support", "content_manager", "customer"):
        actor = await make_account(role)
        for method, url, body in calls:
            _error(await call(method, url, body, actor.headers), 403, "FORBIDDEN")


async def test_concurrent_duplicate_create_is_one_201_and_one_409(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    admin = await make_account("admin")
    text = _text()
    body = {"code": text, "type": "fixed", "value": 1_000}

    responses = await asyncio.gather(
        *(auth_client.post(URL, json=body, headers=admin.headers) for _ in range(2))
    )

    assert sorted(response.status_code for response in responses) == [201, 409]


async def test_list_rejects_bad_query(auth_client: AsyncClient, make_account: MakeAccount) -> None:
    admin = await make_account("admin")
    for params in ({"q": "  "}, {"state": "paused"}, {"sort": "value"}, {"page_size": 5}):
        _error(
            await auth_client.get(URL, params=params, headers=admin.headers),
            400,
            "VALIDATION_ERROR",
        )


async def test_window_is_stored_and_echoed_in_utc(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    admin = await make_account("admin")

    created = await _create(auth_client, admin.headers, starts_at="2030-01-01T03:30:00+03:30")

    assert created["starts_at"] in ("2030-01-01T00:00:00Z", "2030-01-01T00:00:00+00:00")
