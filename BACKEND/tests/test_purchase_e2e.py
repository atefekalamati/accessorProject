"""End-to-end purchase through the public API only (PAY-06, PRD «پرداخت» ✓).

Guest cart → OTP login (merge) → address → checkout validate → order → payment init →
the customer pays at the (fake) gateway → callback → stock committed, code use confirmed,
ordered lines out of the cart, order confirmed. Also: a declined payment retried, and a
payment that lands after the reservation expired (refund_required, D32).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from conftest import Catalog, delete_orders
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from test_cart_merge import _guest_cart, _login, _mobile
from test_checkout_validate import ADDRESS, codes, methods
from test_orders_cancel import _expire_now
from test_orders_create import API, ORDERS

from app.core.time import utc_now
from app.db.models import (
    Address,
    Cart,
    DiscountRedemption,
    InventoryItem,
    Order,
    ProductVariant,
    User,
)

pytestmark = pytest.mark.integration

__all__ = ["codes", "methods"]  # shared fixtures


@pytest_asyncio.fixture
async def customers(
    catalog: Catalog, codes: Any, methods: Any, db_engine: AsyncEngine
) -> AsyncIterator[list[str]]:
    """Mobiles of users made by logging in; their orders, addresses and carts go first."""
    started = utc_now()
    mobiles: list[str] = []
    yield mobiles
    async with AsyncSession(db_engine) as session, session.begin():
        users = list(await session.scalars(select(User.id).where(User.phone.in_(mobiles))))
        orders = list(await session.scalars(select(Order.id).where(Order.user_id.in_(users))))
        await delete_orders(session, orders)
        await session.execute(delete(Address).where(Address.user_id.in_(users)))
        await session.execute(delete(Cart).where(Cart.user_id.in_(users)))
        await session.execute(
            delete(Cart).where(Cart.user_id.is_(None), Cart.created_at >= started)
        )
        await session.execute(delete(User).where(User.id.in_(users)))


class Shopper:
    """One customer driving the API like the storefront would."""

    def __init__(self, client: AsyncClient, headers: dict[str, str]) -> None:
        self.client, self.headers = client, headers

    async def call(self, method: str, path: str, expected: int, **kwargs: Any) -> Any:
        headers = kwargs.pop("headers", self.headers)
        response = await self.client.request(method, f"{API}{path}", headers=headers, **kwargs)
        assert response.status_code == expected, (method, path, response.text)
        return response.json() if response.content else None

    async def checkout(self, body: dict[str, str]) -> dict[str, Any]:
        quote = await self.call("POST", "/checkout/validate", 200, json=body)
        order: dict[str, Any] = await self.call(
            "POST",
            "/orders",
            201,
            json=body | {"fingerprint": quote["fingerprint"]},
            headers=self.headers | {"Idempotency-Key": str(uuid4())},
        )
        assert order["grand_total"] == quote["grand_total"]
        return order

    async def pay(self, order_id: str, **gateway: Any) -> dict[str, Any]:
        started: dict[str, Any] = await self.call(
            "POST",
            "/payments/init",
            201,
            json={"order_id": order_id},
            headers=self.headers | {"Idempotency-Key": str(uuid4())},
        )
        reference = started["redirect_url"].rsplit("/", 1)[1]
        page = await self.call("GET", f"/payments/fake/{reference}", 200)
        assert page["status"] == "pending"
        await self.call(
            "POST", f"/payments/fake/{reference}/complete", 200, json={"result": "paid"} | gateway
        )
        # The gateway's callback carries no session; only the reference matters.
        callback = await self.client.post(f"{API}/payments/callback", json={"reference": reference})
        assert callback.status_code == 200, callback.text
        # The result page reads the order with its own token (SEC-08, ADR-061).
        order = await self.call("GET", f"/orders/{started['order_number']}", 200)
        return {"started": started, "callback": callback.json(), "order": order}


async def _stock(engine: AsyncEngine, variant: ProductVariant) -> tuple[int, int]:
    async with AsyncSession(engine) as session:
        item = (
            await session.scalars(
                select(InventoryItem).where(InventoryItem.variant_id == variant.id)
            )
        ).one()
        return item.total_quantity, item.reserved_quantity


async def _redemption(engine: AsyncEngine, order_id: str) -> str | None:
    async with AsyncSession(engine) as session:
        return await session.scalar(
            select(DiscountRedemption.status).where(DiscountRedemption.order_id == UUID(order_id))
        )


MakeShopper = Callable[..., Awaitable[tuple[Shopper, dict[str, str]]]]


@pytest_asyncio.fixture
async def shopper_from_guest(
    auth_client: AsyncClient,
    issue_otp: Callable[..., Awaitable[Any]],
    methods: Any,
    customers: list[str],
) -> MakeShopper:
    async def make(*lines: tuple[ProductVariant, int]) -> tuple[Shopper, dict[str, str]]:
        await _guest_cart(auth_client, *lines)
        mobile = _mobile()
        customers.append(mobile)
        login = await _login(auth_client, issue_otp, mobile)  # merges the guest cart
        auth_client.cookies.clear()
        shopper = Shopper(auth_client, {"Authorization": f"Bearer {login.json()['access_token']}"})
        address = await shopper.call("POST", "/addresses", 201, json=ADDRESS)
        method = await methods(cost=30_000)
        return shopper, {"address_id": address["id"], "shipping_method_id": str(method.id)}

    return make


async def test_a_purchase_from_guest_cart_to_paid_order(
    catalog: Catalog, codes: Any, shopper_from_guest: MakeShopper, db_engine: AsyncEngine
) -> None:
    ring = await catalog.variant(await catalog.product(), stock=(5, 0, 0), base_price=250_000)
    chain = await catalog.variant(await catalog.product(), stock=(3, 0, 0), base_price=90_000)
    code = await codes(value=20_000)
    shopper, body = await shopper_from_guest((ring, 2), (chain, 1))
    await shopper.call("POST", "/cart/discount", 200, json={"code": code.code})

    order = await shopper.checkout(body)
    assert await _stock(db_engine, ring) == (5, 2)  # reserved for 15 minutes
    paid = await shopper.pay(order["id"])

    assert paid["started"]["amount"] == order["grand_total"]
    assert paid["callback"] == {"outcome": "paid"}
    assert (paid["order"]["status"], paid["order"]["payment_status"]) == ("confirmed", "paid")
    assert paid["order"]["order_number"] == order["order_number"]
    assert await _stock(db_engine, ring) == (3, 0)  # committed
    assert await _stock(db_engine, chain) == (2, 0)
    assert await _redemption(db_engine, order["id"]) == "confirmed"
    cart = await shopper.call("GET", "/cart", 200)
    assert cart["items"] == [] and cart.get("discount") is None
    # The same order cannot be paid twice; nor cancelled once paid.
    again = await shopper.client.post(
        f"{API}/payments/init",
        json={"order_id": order["id"]},
        headers=shopper.headers | {"Idempotency-Key": str(uuid4())},
    )
    assert again.status_code == 422, again.text
    cancelled = await shopper.client.post(f"{ORDERS}/{order['id']}/cancel", headers=shopper.headers)
    assert cancelled.status_code == 422, cancelled.text


async def test_a_declined_payment_is_retried_to_success(
    catalog: Catalog, shopper_from_guest: MakeShopper, db_engine: AsyncEngine
) -> None:
    ring = await catalog.variant(await catalog.product(), stock=(5, 0, 0), base_price=250_000)
    shopper, body = await shopper_from_guest((ring, 1))
    order = await shopper.checkout(body)

    declined = await shopper.pay(order["id"], result="failed")
    assert declined["callback"]["outcome"] == "failed"
    assert await _stock(db_engine, ring) == (5, 1)  # still held for the retry (D34)
    paid = await shopper.pay(order["id"])

    assert paid["callback"]["outcome"] == "paid"
    assert paid["started"]["payment_id"] != declined["started"]["payment_id"]
    assert await _stock(db_engine, ring) == (4, 0)


async def test_a_payment_after_the_reservation_expired_is_refund_required(
    catalog: Catalog, shopper_from_guest: MakeShopper, db_engine: AsyncEngine
) -> None:
    ring = await catalog.variant(await catalog.product(), stock=(5, 0, 0), base_price=250_000)
    shopper, body = await shopper_from_guest((ring, 1))
    order = await shopper.checkout(body)
    started = await shopper.call(
        "POST",
        "/payments/init",
        201,
        json={"order_id": order["id"]},
        headers=shopper.headers | {"Idempotency-Key": str(uuid4())},
    )
    reference = started["redirect_url"].rsplit("/", 1)[1]
    await shopper.call("POST", f"/payments/fake/{reference}/complete", 200, json={"result": "paid"})
    await _expire_now(db_engine, UUID(order["id"]))  # the customer took too long

    callback = await shopper.client.post(f"{API}/payments/callback", json={"reference": reference})

    assert callback.status_code == 200, callback.text
    assert callback.json() == {"outcome": "refund_required"}
    seen = await shopper.call("GET", f"/orders/{order['order_number']}", 200)
    assert (seen["status"], seen["payment_status"]) == ("cancelled", "refund_required")
    assert await _stock(db_engine, ring) == (5, 0)  # never consumed
    # The cart was not emptied: the customer can order again (D33).
    assert (await shopper.call("GET", "/cart", 200))["items"]
