"""IDOR: no customer can read or change another customer's resources (ACC-02, ADR-018).

Every endpoint that takes the id of an owned resource answers 404 for someone else's
(never 403, so existence does not leak) and changes nothing; lists never include it.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from conftest import Account, Catalog
from httpx import AsyncClient, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from test_checkout_validate import ITEMS, _add
from test_orders_create import (
    API,
    ORDERS,
    Buyer,
    MakeBuyer,
    _orders_go_first,
    buyer,
    codes,
    methods,
    shopper,
)
from test_payments_init import INIT

from app.db.models import Address, CartItem, Order, Payment

pytestmark = pytest.mark.integration

__all__ = ["_orders_go_first", "buyer", "codes", "methods", "shopper"]  # shared fixtures

ADDRESSES = f"{API}/addresses"


def _not_found(response: Response) -> None:
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def _snapshot(
    engine: AsyncEngine, victim: Buyer, order_id: UUID, line_id: UUID
) -> dict[str, Any]:
    """Everything an attack could change on the victim's side."""
    async with AsyncSession(engine) as session:
        order = await session.get(Order, order_id)
        assert order is not None
        addresses = (
            await session.execute(
                select(Address.id, Address.recipient_name, Address.is_default).where(
                    Address.user_id == victim.account.id
                )
            )
        ).all()
        line = await session.scalar(select(CartItem.quantity).where(CartItem.id == line_id))
        payments = await session.scalar(
            select(func.count()).select_from(Payment).where(Payment.order_id == order_id)
        )
        return {
            "order": (order.status, order.payment_status, order.updated_at),
            "addresses": sorted(addresses),
            "line": line,
            "payments": payments,
        }


async def test_another_customers_resources_are_404_and_untouched(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    product = await catalog.product()
    variant = await catalog.variant(product, stock=(10, 0, 0))
    victim = await buyer((variant, 1))
    placed = await victim.order()
    assert placed.status_code == 201, placed.text
    order = placed.json()
    order_id = UUID(order["id"])
    line_id = await _add(auth_client, victim.account, variant, 1)
    address_id = victim.address_id

    attacker: Account = (await buyer((variant, 1))).account
    before = await _snapshot(db_engine, victim, order_id, UUID(line_id))
    headers = attacker.headers

    # Orders: detail, cancel, payment.
    _not_found(await auth_client.get(f"{ORDERS}/{order['order_number']}", headers=headers))
    _not_found(await auth_client.post(f"{ORDERS}/{order_id}/cancel", headers=headers))
    _not_found(
        await auth_client.post(
            INIT,
            json={"order_id": str(order_id)},
            headers=headers | {"Idempotency-Key": "idor-1"},
        )
    )
    # Addresses: read, change, delete.
    _not_found(await auth_client.get(f"{ADDRESSES}/{address_id}", headers=headers))
    _not_found(
        await auth_client.patch(
            f"{ADDRESSES}/{address_id}", json={"recipient_name": "Mallory"}, headers=headers
        )
    )
    _not_found(await auth_client.delete(f"{ADDRESSES}/{address_id}", headers=headers))
    # Cart lines: change and delete.
    _not_found(await auth_client.patch(f"{ITEMS}/{line_id}", json={"quantity": 5}, headers=headers))
    _not_found(await auth_client.delete(f"{ITEMS}/{line_id}", headers=headers))
    # Checkout and ordering with the victim's address.
    body = {"address_id": address_id, "shipping_method_id": str(victim.method.id)}
    _not_found(await auth_client.post(f"{API}/checkout/validate", json=body, headers=headers))

    assert await _snapshot(db_engine, victim, order_id, UUID(line_id)) == before

    # Lists show only the caller's own rows.
    orders = await auth_client.get(ORDERS, headers=headers)
    assert str(order_id) not in {item["id"] for item in orders.json()["items"]}
    addresses = await auth_client.get(ADDRESSES, headers=headers)
    assert address_id not in {item["id"] for item in addresses.json()}
    cart = await auth_client.get(f"{API}/cart", headers=headers)
    assert line_id not in {item["id"] for item in cart.json()["items"]}


async def test_a_guest_cart_line_belongs_to_its_cookie(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer
) -> None:
    product = await catalog.product()
    variant = await catalog.variant(product, stock=(10, 0, 0))
    customer = (await buyer((variant, 1))).account
    added = await auth_client.post(
        ITEMS, json={"variant_id": str(variant.id), "quantity": 1}, headers=customer.headers
    )
    line_id = added.json()["id"]

    # A guest (no token, a fresh cookie jar) cannot touch a customer's line.
    async with AsyncClient(transport=auth_client._transport, base_url="http://testserver") as guest:
        _not_found(await guest.patch(f"{ITEMS}/{line_id}", json={"quantity": 3}))
        _not_found(await guest.delete(f"{ITEMS}/{line_id}"))
