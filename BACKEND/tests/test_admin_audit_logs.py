"""The audit log viewer: super admin only, filters, newest first (ADM-06)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from conftest import MakeAccount
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.time import utc_now
from app.db.models import AuditLog

pytestmark = pytest.mark.integration

AUDIT = "/api/v1/admin/audit-logs"


async def _write(engine: AsyncEngine, entity_id: UUID, *actions: str) -> None:
    now = utc_now()
    async with AsyncSession(engine) as session, session.begin():
        session.add_all(
            AuditLog(
                action=action,
                entity_type="order",
                entity_id=entity_id,
                metadata_={"diff": {}},
                created_at=now + timedelta(seconds=index),
            )
            for index, action in enumerate(actions)
        )


async def _items(client: AsyncClient, headers: dict[str, str], **params: Any) -> list[str]:
    response = await client.get(AUDIT, params=params, headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return [item["action"] for item in response.json()["items"]]


async def test_super_admin_filters_the_log(
    auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
) -> None:
    root = await make_account("super_admin")
    entity = uuid4()
    await _write(db_engine, entity, "order.created", "order.status_changed", "payment.paid")
    headers = root.headers

    assert await _items(auth_client, headers, entity_id=str(entity)) == [
        "payment.paid",
        "order.status_changed",
        "order.created",
    ]
    assert await _items(auth_client, headers, entity_id=str(entity), action="order.") == [
        "order.status_changed",
        "order.created",
    ]
    assert await _items(auth_client, headers, entity_id=str(entity), action="order.created") == [
        "order.created"
    ]
    # "order" without the dot is an exact match: nothing is called just "order".
    assert await _items(auth_client, headers, entity_id=str(entity), action="order") == []
    later = (utc_now() + timedelta(hours=1)).isoformat()
    assert await _items(auth_client, headers, entity_id=str(entity), **{"from": later}) == []
    detail = (
        await auth_client.get(AUDIT, params={"entity_id": str(entity)}, headers=headers)
    ).json()
    assert set(detail["items"][0]) == {
        "id",
        "actor_user_id",
        "action",
        "entity_type",
        "entity_id",
        "metadata",
        "ip",
        "created_at",
    }


async def test_only_super_admin_and_validation(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    root = await make_account("super_admin")
    assert (await auth_client.get(AUDIT)).status_code == 401
    assert (await auth_client.get(f"{AUDIT}?x=1")).status_code == 401
    for role in ("admin", "support", "content_manager", "customer"):
        account = await make_account(role)
        response = await auth_client.get(AUDIT, headers=account.headers)
        assert response.status_code == 403, role
    for params in (
        {"x": "1"},
        {"action": "Order.Created"},
        {"action": "a%"},
        {"entity_type": "Order"},
        {"actor_user_id": "me"},
        {"from": "2026-10-01T00:00:00"},
    ):
        response = await auth_client.get(AUDIT, params=params, headers=root.headers)
        assert response.status_code == 400, params
    for method in ("post", "patch", "delete"):
        response = await auth_client.request(method.upper(), AUDIT, headers=root.headers)
        assert response.status_code == 405, method
