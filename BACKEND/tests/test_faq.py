"""FAQ: public grouping and order, admin CRUD, Markdown rule, audit, access (CNT-05)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from conftest import MakeAccount
from httpx import AsyncClient, Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.time import utc_now
from app.db.models import AuditLog, FaqItem
from app.db.models.content import MAX_FAQ_ANSWER_LENGTH

pytestmark = pytest.mark.integration

URL = "/api/v1/admin/faq"
PUBLIC_URL = "/api/v1/faq"


def _error(response: Response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code


@pytest_asyncio.fixture(autouse=True)
async def _cleanup(db_engine: AsyncEngine) -> AsyncIterator[None]:
    started = utc_now()
    yield
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(FaqItem).where(FaqItem.created_at >= started))


async def _create(client: AsyncClient, headers: dict[str, str], **fields: Any) -> dict[str, Any]:
    body = {"group_title": "Shipping", "question": "How long?", "answer": "**3** days"} | fields
    response = await client.post(URL, json=body, headers=headers)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


async def _actions(engine: AsyncEngine, item_id: str) -> list[str]:
    async with AsyncSession(engine) as session:
        statement = (
            select(AuditLog.action)
            .where(AuditLog.entity_id == item_id)
            .order_by(AuditLog.created_at, AuditLog.id)
        )
        return list(await session.scalars(statement))


async def test_public_groups_only_published_items_in_a_stable_order(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    editor = await make_account("content_manager")
    tag = uuid4().hex[:8]
    first_group, second_group = f"First {tag}", f"Second {tag}"
    late = await _create(
        auth_client, editor.headers, group_title=first_group, display_order=30, is_published=True
    )
    await _create(
        auth_client, editor.headers, group_title=second_group, display_order=20, is_published=True
    )
    early = await _create(
        auth_client, editor.headers, group_title=first_group, display_order=10, is_published=True
    )
    await _create(auth_client, editor.headers, group_title=first_group, display_order=5)

    response = await auth_client.get(PUBLIC_URL)

    assert response.status_code == 200, response.text
    groups = [group for group in response.json()["groups"] if tag in group["title"]]
    assert [group["title"] for group in groups] == [first_group, second_group]
    assert [item["id"] for item in groups[0]["items"]] == [early["id"], late["id"]]
    assert set(groups[0]["items"][0]) == {"id", "question", "answer"}


async def test_same_order_falls_back_to_id(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    editor = await make_account("content_manager")
    group = f"Tie {uuid4().hex[:8]}"
    ids = [
        (await _create(auth_client, editor.headers, group_title=group, is_published=True))["id"]
        for _ in range(4)
    ]

    response = await auth_client.get(PUBLIC_URL)

    [listed] = [item for item in response.json()["groups"] if item["title"] == group]
    assert [item["id"] for item in listed["items"]] == sorted(ids)


@pytest.mark.parametrize("answer", ["<b>x</b>", "x" * (MAX_FAQ_ANSWER_LENGTH + 1), "  "])
async def test_invalid_answer_is_400(
    auth_client: AsyncClient, make_account: MakeAccount, answer: str
) -> None:
    editor = await make_account("content_manager")
    item = await _create(auth_client, editor.headers)
    body = {"group_title": "G", "question": "Q", "answer": answer}

    _error(await auth_client.post(URL, json=body, headers=editor.headers), 400, "VALIDATION_ERROR")
    _error(
        await auth_client.patch(
            f"{URL}/{item['id']}", json={"answer": answer}, headers=editor.headers
        ),
        400,
        "VALIDATION_ERROR",
    )


@pytest.mark.parametrize(
    "body", [{}, {"question": None}, {"is_published": "yes"}, {"display_order": -1}, {"x": 1}]
)
async def test_invalid_patch_is_400(
    auth_client: AsyncClient, make_account: MakeAccount, body: dict[str, Any]
) -> None:
    editor = await make_account("content_manager")
    item = await _create(auth_client, editor.headers)

    response = await auth_client.patch(f"{URL}/{item['id']}", json=body, headers=editor.headers)

    _error(response, 400, "VALIDATION_ERROR")


async def test_writes_are_audited_and_an_unchanged_patch_is_not(
    auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
) -> None:
    editor = await make_account("admin")
    item = await _create(auth_client, editor.headers, question="Old?")

    same = await auth_client.patch(
        f"{URL}/{item['id']}", json={"question": "Old?"}, headers=editor.headers
    )
    assert same.status_code == 200, same.text
    changed = await auth_client.patch(
        f"{URL}/{item['id']}", json={"is_published": True}, headers=editor.headers
    )
    assert changed.json()["is_published"] is True
    assert (
        await auth_client.delete(f"{URL}/{item['id']}", headers=editor.headers)
    ).status_code == 204

    assert await _actions(db_engine, item["id"]) == [
        "faq_item.created",
        "faq_item.updated",
        "faq_item.deleted",
    ]


async def test_deleted_item_is_gone_everywhere(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    editor = await make_account("content_manager")
    group = f"Gone {uuid4().hex[:8]}"
    item = await _create(auth_client, editor.headers, group_title=group, is_published=True)
    await auth_client.delete(f"{URL}/{item['id']}", headers=editor.headers)

    public = await auth_client.get(PUBLIC_URL)
    assert group not in {entry["title"] for entry in public.json()["groups"]}
    listed = await auth_client.get(URL, params={"limit": 100}, headers=editor.headers)
    assert item["id"] not in {entry["id"] for entry in listed.json()["items"]}
    _error(
        await auth_client.patch(
            f"{URL}/{item['id']}", json={"question": "Q"}, headers=editor.headers
        ),
        404,
        "NOT_FOUND",
    )
    _error(
        await auth_client.delete(f"{URL}/{item['id']}", headers=editor.headers), 404, "NOT_FOUND"
    )


async def test_system_fields_are_ignored(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    editor = await make_account("content_manager")
    forged = str(uuid4())

    item = await _create(auth_client, editor.headers, id=forged, created_by=forged)

    assert item["id"] != forged


@pytest.mark.parametrize("role", ["customer", "support"])
async def test_other_roles_are_403(
    auth_client: AsyncClient, make_account: MakeAccount, role: str
) -> None:
    account = await make_account(role)

    _error(await auth_client.get(URL, headers=account.headers), 403, "FORBIDDEN")


async def test_anonymous_admin_is_401_and_public_needs_no_login(auth_client: AsyncClient) -> None:
    _error(await auth_client.get(URL), 401, "UNAUTHORIZED")
    assert (await auth_client.get(PUBLIC_URL)).status_code == 200
