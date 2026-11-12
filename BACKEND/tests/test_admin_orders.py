"""Admin orders and payments: lists, filters and detail (ADM-01, D38)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from conftest import Account, Catalog, MakeAccount, nested_keys
from httpx import AsyncClient
from test_orders_create import (
    API,
    Buyer,
    MakeBuyer,
    _error,
    _orders_go_first,
    buyer,
    codes,
    methods,
    shopper,
)
from test_payments_init import _init

from app.core.time import utc_now

pytestmark = pytest.mark.integration

__all__ = ["_orders_go_first", "buyer", "codes", "methods", "shopper"]  # shared fixtures

ORDERS = f"{API}/admin/orders"
PAYMENTS = f"{API}/admin/payments"


async def _placed(catalog: Catalog, buyer: MakeBuyer) -> tuple[Buyer, dict[str, Any]]:
    product = await catalog.product()
    variant = await catalog.variant(product, stock=(10, 0, 0))
    ready = await buyer((variant, 3))
    response = await ready.order()
    assert response.status_code == 201, response.text
    return ready, response.json()


async def _list(client: AsyncClient, staff: Account, url: str, **params: Any) -> dict[str, Any]:
    response = await client.get(url, params=params, headers=staff.headers)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body: dict[str, Any] = response.json()
    return body


async def test_list_masks_the_mobile_and_filters(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, make_account: MakeAccount
) -> None:
    support = await make_account("support")
    ready, placed = await _placed(catalog, buyer)
    number = placed["order_number"]

    body = await _list(auth_client, support, ORDERS, q=number)
    [row] = body["items"]
    assert row["order_number"] == number
    assert row["item_count"] == 3
    assert "***" in row["phone"]
    assert row["user_id"] == str(ready.account.id)

    # A number prefix (any case), and digits of the full mobile from the detail.
    assert (await _list(auth_client, support, ORDERS, q=number[:8].lower()))["total"] >= 1
    detail = await auth_client.get(f"{ORDERS}/{placed['id']}", headers=support.headers)
    by_mobile = await _list(auth_client, support, ORDERS, q=detail.json()["phone"][-8:], limit=100)
    assert number in {item["order_number"] for item in by_mobile["items"]}
    for params in (
        {"status": "pending_payment"},
        {"payment_status": "unpaid"},
        {"shipment_status": "not_shipped"},
        {"from": (utc_now() - timedelta(minutes=5)).isoformat()},
    ):
        found = await _list(auth_client, support, ORDERS, q=number, **params)
        assert found["total"] == 1, params
    for params in (
        {"status": "cancelled"},
        {"payment_status": "paid"},
        {"to": (utc_now() - timedelta(minutes=5)).isoformat()},
    ):
        assert (await _list(auth_client, support, ORDERS, q=number, **params))["total"] == 0


async def test_detail_has_lines_payments_and_history_with_actors(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, make_account: MakeAccount
) -> None:
    admin = await make_account("admin")
    ready, placed = await _placed(catalog, buyer)
    assert (await _init(ready, UUID(placed["id"]))).status_code == 201

    response = await auth_client.get(f"{ORDERS}/{placed['id']}", headers=admin.headers)

    assert response.status_code == 200, response.text
    body = response.json()
    # Everything POST /orders returned; only the payment status moved (init).
    assert {key: body[key] for key in placed} == placed | {"payment_status": "pending"}
    assert body["phone"].startswith("+98") and "***" not in body["phone"]
    [payment] = body["payments"]
    assert payment["status"] == "pending" and payment["gateway_reference"]
    assert "raw_event" not in nested_keys(body)
    assert {"actor_user_id", "reason"} <= set(body["history"][0])
    # The customer's cancel and init are attributed to the customer.
    assert str(ready.account.id) in {row["actor_user_id"] for row in body["history"]}

    payments = await _list(auth_client, admin, PAYMENTS, status="pending", limit=100)
    assert placed["order_number"] in {row["order_number"] for row in payments["items"]}


async def test_payments_filter_by_failure_reason(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    admin = await make_account("admin")

    body = await _list(auth_client, admin, PAYMENTS, failure_reason="no-such-reason")

    assert body["total"] == 0


async def test_permissions_and_validation(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    customer = await make_account("customer")
    editor = await make_account("content_manager")
    admin = await make_account("admin")

    for url in (ORDERS, f"{ORDERS}/{uuid4()}", PAYMENTS):
        _error(await auth_client.get(url), 401, "UNAUTHORIZED")
        _error(await auth_client.get(f"{url}?bogus=1"), 401, "UNAUTHORIZED")
        for account in (customer, editor):
            _error(await auth_client.get(url, headers=account.headers), 403, "FORBIDDEN")
    _error(await auth_client.get(f"{ORDERS}/{uuid4()}", headers=admin.headers), 404, "NOT_FOUND")
    for params in (
        {"bogus": "1"},
        {"status": "lost"},
        {"q": "hello"},
        {"q": "12"},
        {"from": "2026-10-01T00:00:00"},
        {"from": "2026-10-02T00:00:00Z", "to": "2026-10-01T00:00:00Z"},
        {"sort": "total"},
    ):
        response = await auth_client.get(ORDERS, params=params, headers=admin.headers)
        _error(response, 400, "VALIDATION_ERROR")
    _error(
        await auth_client.get(f"{ORDERS}/not-a-uuid", headers=admin.headers),
        400,
        "VALIDATION_ERROR",
    )
