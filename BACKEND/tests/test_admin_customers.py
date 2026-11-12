"""Customers in the admin panel: masked list, audited detail (ADM-03, D38)."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from conftest import Catalog, MakeAccount, nested_keys
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from test_orders_create import (
    API,
    MakeBuyer,
    _error,
    _orders_go_first,
    buyer,
    codes,
    methods,
    shopper,
)

from app.db.models import AuditLog, User

pytestmark = pytest.mark.integration

__all__ = ["_orders_go_first", "buyer", "codes", "methods", "shopper"]  # shared fixtures

CUSTOMERS = f"{API}/admin/customers"
SECRET_KEYS = {"refresh_token_hash", "code_hash", "otp", "token", "session", "sessions"}


async def _phone(engine: AsyncEngine, user_id: Any) -> str:
    async with AsyncSession(engine) as session:
        phone: str = (await session.scalars(select(User.phone).where(User.id == user_id))).one()
        return phone


async def test_list_masks_and_detail_shows_and_audits(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    make_account: MakeAccount,
    db_engine: AsyncEngine,
) -> None:
    support = await make_account("support")
    product = await catalog.product()
    variant = await catalog.variant(product, stock=(10, 0, 0))
    ready = await buyer((variant, 1))
    placed = await ready.order()
    assert placed.status_code == 201
    phone = await _phone(db_engine, ready.account.id)

    listed = await auth_client.get(CUSTOMERS, params={"q": phone[-8:]}, headers=support.headers)
    assert listed.status_code == 200, listed.text
    assert listed.headers["cache-control"] == "no-store"
    [row] = [item for item in listed.json()["items"] if item["id"] == str(ready.account.id)]
    assert row["phone"] != phone and "***" in row["phone"]
    assert row["order_count"] == 1

    detail = await auth_client.get(f"{CUSTOMERS}/{ready.account.id}", headers=support.headers)

    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["phone"] == phone
    assert len(body["addresses"]) == 1
    assert body["order_count"] == 1 and body["paid_total"] == 0
    assert [order["order_number"] for order in body["recent_orders"]] == [
        placed.json()["order_number"]
    ]
    assert not nested_keys(body) & SECRET_KEYS
    async with AsyncSession(db_engine) as session:
        audits = list(
            await session.scalars(
                select(AuditLog).where(
                    AuditLog.action == "customer.viewed",
                    AuditLog.entity_id == ready.account.id,
                )
            )
        )
    assert [audit.actor_user_id for audit in audits] == [support.id]
    assert phone not in str(audits[0].metadata_)


async def test_staff_are_not_customers_and_permissions(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    admin = await make_account("admin")
    editor = await make_account("content_manager")
    customer = await make_account("customer")

    _error(
        await auth_client.get(f"{CUSTOMERS}/{editor.id}", headers=admin.headers), 404, "NOT_FOUND"
    )
    _error(await auth_client.get(f"{CUSTOMERS}/{uuid4()}", headers=admin.headers), 404, "NOT_FOUND")
    for url in (CUSTOMERS, f"{CUSTOMERS}/{customer.id}"):
        _error(await auth_client.get(url), 401, "UNAUTHORIZED")
        _error(await auth_client.get(f"{url}?x=1"), 401, "UNAUTHORIZED")
        for account in (editor, customer):
            _error(await auth_client.get(url, headers=account.headers), 403, "FORBIDDEN")
    for params in ({"x": "1"}, {"q": "a"}, {"status": "gone"}, {"sort": "name"}):
        _error(
            await auth_client.get(CUSTOMERS, params=params, headers=admin.headers),
            400,
            "VALIDATION_ERROR",
        )
    by_status = await auth_client.get(
        CUSTOMERS, params={"status": "active", "limit": 100}, headers=admin.headers
    )
    assert str(editor.id) not in {item["id"] for item in by_status.json()["items"]}
