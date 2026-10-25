"""POST /orders: snapshot, reservation, redemption, idempotency, locks (ORD-04, ADR-048)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from conftest import Account, Catalog, MakeAccount, delete_orders
from httpx import AsyncClient, Response
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from test_checkout_validate import _add, _address, _item_id, codes, methods, shopper

from app.core.time import utc_now
from app.db.models import (
    AuditLog,
    DiscountCode,
    DiscountRedemption,
    IdempotencyKey,
    InventoryItem,
    InventoryReservation,
    Order,
    OrderAddress,
    OrderItem,
    OrderPriceSnapshot,
    OrderStatusHistory,
    ProductVariant,
)
from app.modules.checkout.service import CheckoutService
from app.modules.discounts.redemption import RedemptionService
from app.modules.discounts.rules import Rejection, discount_error
from app.modules.inventory.jobs import sweep_expired_reservations
from app.modules.inventory.reservation import RESERVATION_TTL
from app.modules.orders.schemas import CreateOrderRequest
from app.modules.orders.service import OrderService

pytestmark = pytest.mark.integration

__all__ = ["codes", "methods", "shopper"]  # fixtures shared with the checkout tests

API = "/api/v1"
ORDERS = f"{API}/orders"
VALIDATE = f"{API}/checkout/validate"


@pytest_asyncio.fixture(autouse=True)
async def _orders_go_first(
    catalog: Catalog, shopper: Any, methods: Any, codes: Any, db_engine: AsyncEngine
) -> AsyncIterator[None]:
    """Orders reference users, variants, codes and methods (RESTRICT): remove this test's
    orders before ``catalog``, ``shopper`` (users), ``methods`` and ``codes`` tear down
    (this fixture depends on them, so it goes first)."""
    started = utc_now() - timedelta(days=400)
    yield
    async with AsyncSession(db_engine) as session, session.begin():
        ids = list(await session.scalars(select(Order.id).where(Order.created_at >= started)))
        await delete_orders(session, ids)


class Buyer:
    """A customer with a cart, an address and a shipping method ready to order."""

    def __init__(self, client: AsyncClient, account: Account, address_id: str, method: Any):
        self.client, self.account, self.address_id, self.method = (
            client,
            account,
            address_id,
            method,
        )

    @property
    def body(self) -> dict[str, str]:
        return {"address_id": self.address_id, "shipping_method_id": str(self.method.id)}

    async def quote(self) -> dict[str, Any]:
        response = await self.client.post(VALIDATE, json=self.body, headers=self.account.headers)
        assert response.status_code == 200, response.text
        quoted: dict[str, Any] = response.json()
        return quoted

    async def order(self, key: str | None = None, fingerprint: str | None = None) -> Response:
        if fingerprint is None:
            fingerprint = (await self.quote())["fingerprint"]
        headers = dict(self.account.headers)
        headers["Idempotency-Key"] = key or str(uuid4())
        return await self.client.post(
            ORDERS, json=self.body | {"fingerprint": fingerprint}, headers=headers
        )


MakeBuyer = Callable[..., Awaitable[Buyer]]


@pytest_asyncio.fixture
async def buyer(auth_client: AsyncClient, shopper: Any, methods: Any) -> MakeBuyer:
    async def make(*lines: tuple[ProductVariant, int], **method: Any) -> Buyer:
        account = await shopper()
        for variant, quantity in lines:
            await _add(auth_client, account, variant, quantity)
        address_id = await _address(auth_client, account)
        return Buyer(auth_client, account, address_id, await methods(**({"cost": 30_000} | method)))

    return make


def _error(response: Response, status: int, code: str, kind: str | None = None) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body: dict[str, Any] = response.json()["error"]
    assert body["code"] == code
    if kind is not None:
        assert body["details"][0]["type"] == kind
    return body


async def _count(engine: AsyncEngine, model: Any, *where: Any) -> int:
    async with AsyncSession(engine) as session:
        return int(await session.scalar(select(func.count()).select_from(model).where(*where)) or 0)


async def _orders_of(engine: AsyncEngine, user_id: UUID) -> list[Order]:
    async with AsyncSession(engine) as session:
        return list(await session.scalars(select(Order).where(Order.user_id == user_id)))


# --- the order -------------------------------------------------------------------------


async def test_an_order_snapshots_reserves_and_keeps_the_cart(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    product = await catalog.product(title="Silver ring")
    red = await catalog.variant(
        product, stock=(5, 0, 0), base_price=100_000, options={"color": "Red"}
    )
    blue = await catalog.variant(product, stock=(5, 0, 0), base_price=50_000)
    ready = await buyer((red, 1), (blue, 2), free_shipping_threshold=10_000_000)
    quote = await ready.quote()

    response = await ready.order(fingerprint=quote["fingerprint"])

    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["order_number"].startswith(f"ORD-{utc_now().year}-")
    assert (body["status"], body["payment_status"], body["shipment_status"]) == (
        "pending_payment",
        "unpaid",
        "not_shipped",
    )
    for field in ("subtotal", "tax_amount", "shipping_amount", "grand_total"):
        assert body[field] == quote[field], field
    # Lines in the stable pricing order (by cart line id), as quoted.
    assert [item["variant_id"] for item in body["items"]] == [
        item["variant_id"] for item in quote["items"]
    ]
    red_line = next(item for item in body["items"] if item["variant_id"] == str(red.id))
    assert (red_line["product_title"], red_line["variant_label"]) == ("Silver ring", "color: Red")
    assert body["address"]["phone"] == "+989121234567"
    assert body["shipping"] == {
        "method_id": str(ready.method.id),
        "title": ready.method.title,
        "amount": 30_000,
    }
    created = datetime.fromisoformat(body["created_at"])
    assert datetime.fromisoformat(body["reservation_expires_at"]) == created + RESERVATION_TTL

    order_id = UUID(body["id"])
    async with AsyncSession(db_engine) as session:
        items = list(
            await session.scalars(
                select(OrderItem).where(OrderItem.order_id == order_id).order_by(OrderItem.position)
            )
        )
        snapshot = await session.get(OrderPriceSnapshot, order_id)
        address = await session.get(OrderAddress, order_id)
        reservation = (
            await session.scalars(
                select(InventoryReservation).where(InventoryReservation.order_id == order_id)
            )
        ).one()
        history = list(
            await session.scalars(
                select(OrderStatusHistory.field).where(OrderStatusHistory.order_id == order_id)
            )
        )
    assert [item.position for item in items] == [0, 1]
    assert snapshot is not None and snapshot.fingerprint == quote["fingerprint"]
    assert address is not None and address.source_address_id == UUID(ready.address_id)
    assert reservation.status == "active"
    assert sorted(history) == ["order", "payment", "shipment"]
    assert (
        await _count(
            db_engine, AuditLog, AuditLog.entity_id == order_id, AuditLog.action == "order.created"
        )
        == 1
    )
    # The cart is not emptied (D34): only a paid order removes its lines.
    cart = await auth_client.get(f"{API}/cart", headers=ready.account.headers)
    assert len(cart.json()["items"]) == 2


async def test_a_code_is_redeemed_pending(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, codes: Any, db_engine: AsyncEngine
) -> None:
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0), base_price=100_000)
    ready = await buyer((variant, 2))
    code = await codes(value=20_000)
    await auth_client.post(
        f"{API}/cart/discount", json={"code": code.code}, headers=ready.account.headers
    )

    response = await ready.order()

    assert response.status_code == 201, response.text
    assert response.json()["discount"] == {"code": code.code, "amount": 20_000}
    async with AsyncSession(db_engine) as session:
        redemption = (
            await session.scalars(
                select(DiscountRedemption).where(
                    DiscountRedemption.order_id == UUID(response.json()["id"])
                )
            )
        ).one()
    assert (redemption.status, redemption.amount) == ("pending", 20_000)


# --- idempotency and one live pending order --------------------------------------------


async def test_replay_reuse_and_one_live_pending_order(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0))
    ready = await buyer((variant, 1))
    quote = await ready.quote()
    key = str(uuid4())

    first = await ready.order(key, quote["fingerprint"])
    again = await ready.order(key, quote["fingerprint"])
    reused = await ready.order(key, "0" * 64)
    second = await ready.order(str(uuid4()), quote["fingerprint"])

    assert first.status_code == again.status_code == 201
    assert again.json() == first.json()
    _error(reused, 422, "IDEMPOTENCY_KEY_REUSED")
    pending = _error(second, 409, "ORDER_PENDING", "order_pending")
    assert pending["details"][0]["order_number"] == first.json()["order_number"]
    assert len(await _orders_of(db_engine, ready.account.id)) == 1

    # Once its reservation expires the order no longer blocks a new one; the old order
    # stays pending_payment until the expiry job cancels it (ORD-06).
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            update(InventoryReservation)
            .where(InventoryReservation.order_id == UUID(first.json()["id"]))
            .values(expires_at=utc_now() - timedelta(seconds=1))
        )
    third = await ready.order()
    assert third.status_code == 201, third.text
    # A replay still returns the original response, now stale (ADR-046).
    assert (await ready.order(key, quote["fingerprint"])).json() == first.json()


async def test_header_and_body_errors(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer
) -> None:
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0))
    ready = await buyer((variant, 1))
    body = ready.body | {"fingerprint": "a" * 64}
    _error(await auth_client.post(ORDERS, json=body), 401, "UNAUTHORIZED")
    _error(
        await auth_client.post(ORDERS, json={"x": 1}, headers={"Idempotency-Key": "k"}),
        401,
        "UNAUTHORIZED",
    )
    # An unknown query parameter never answers before 401 either.
    _error(await auth_client.post(f"{ORDERS}?x=1", json=body), 401, "UNAUTHORIZED")
    headers = ready.account.headers
    _error(
        await auth_client.post(
            f"{ORDERS}?x=1", json=body, headers=headers | {"Idempotency-Key": "k-q"}
        ),
        400,
        "VALIDATION_ERROR",
    )
    _error(await auth_client.post(ORDERS, json=body, headers=headers), 400, "VALIDATION_ERROR")
    keyed = headers | {"Idempotency-Key": "k-1"}
    for bad in (
        ready.body,
        body | {"fingerprint": "XYZ"},
        body | {"grand_total": 1},
        body | {"address_id": "nope"},
    ):
        _error(await auth_client.post(ORDERS, json=bad, headers=keyed), 400, "VALIDATION_ERROR")


async def test_a_stale_quote_is_409_with_the_new_quote_and_stores_nothing(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0), base_price=100_000)
    ready = await buyer((variant, 1))
    old = await ready.quote()
    await catalog.set(ProductVariant, variant.id, base_price=120_000, price_version=3)
    key = str(uuid4())

    stale = await ready.order(key, old["fingerprint"])

    body = _error(stale, 409, "PRICE_CHANGED", "price_changed")
    assert stale.headers["cache-control"] == "no-store"
    fresh = body["details"][0]["quote"]
    assert fresh["subtotal"] == 120_000 and fresh["fingerprint"] != old["fingerprint"]
    assert await _orders_of(db_engine, ready.account.id) == []
    assert await _count(db_engine, IdempotencyKey, IdempotencyKey.user_id == ready.account.id) == 0
    # A failed attempt stored nothing: the same key now places the order.
    retried = await ready.order(key, fresh["fingerprint"])
    assert retried.status_code == 201, retried.text


async def test_business_errors_leave_nothing_behind(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    shopper: Any,
    methods: Any,
    codes: Any,
    db_engine: AsyncEngine,
) -> None:
    variant = await catalog.variant(await catalog.product(), stock=(3, 0, 0), base_price=100_000)
    ready = await buyer((variant, 2))
    quote = await ready.quote()
    key = str(uuid4())

    # Another user's address: 404.
    other = await shopper()
    others_address = await _address(auth_client, other)
    response = await auth_client.post(
        ORDERS,
        json={**ready.body, "address_id": others_address, "fingerprint": quote["fingerprint"]},
        headers=ready.account.headers | {"Idempotency-Key": key},
    )
    _error(response, 404, "NOT_FOUND")

    # Two units are held elsewhere: only one is free (the reservation is the check).
    await catalog.set(InventoryItem, await _item_id(db_engine, variant.id), reserved_quantity=2)
    _error(await ready.order(key, quote["fingerprint"]), 409, "INSUFFICIENT_STOCK")
    await catalog.set(InventoryItem, await _item_id(db_engine, variant.id), reserved_quantity=0)

    # The code stops applying after the quote: 422; its value changes: 409 with a quote.
    code = await codes(value=10_000)
    await auth_client.post(
        f"{API}/cart/discount", json={"code": code.code}, headers=ready.account.headers
    )
    with_code = await ready.quote()
    await catalog.set(DiscountCode, code.id, value=15_000)
    _error(await ready.order(key, with_code["fingerprint"]), 409, "PRICE_CHANGED")
    await catalog.set(DiscountCode, code.id, is_active=False)
    _error(
        await ready.order(key, with_code["fingerprint"]), 422, "DISCOUNT_NOT_APPLICABLE", "invalid"
    )
    await auth_client.delete(f"{API}/cart/discount", headers=ready.account.headers)

    # An inactive method: 422; a deleted variant: 422 (SD rule).
    await catalog.set(type(ready.method), ready.method.id, is_active=False)
    _error(await ready.order(key, quote["fingerprint"]), 422, "BUSINESS_RULE_VIOLATION")
    await catalog.set(type(ready.method), ready.method.id, is_active=True)
    await catalog.set(ProductVariant, variant.id, deleted_at=utc_now())
    response = await ready.order(key, quote["fingerprint"])
    _error(response, 422, "BUSINESS_RULE_VIOLATION", "line_unavailable")

    assert await _orders_of(db_engine, ready.account.id) == []
    assert await _count(db_engine, IdempotencyKey, IdempotencyKey.user_id == ready.account.id) == 0
    empty = await buyer()
    _error(await empty.order(fingerprint="a" * 64), 422, "BUSINESS_RULE_VIOLATION", "cart_empty")


async def test_a_failure_after_the_reservation_rolls_everything_back(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    codes: Any,
    db_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0))
    ready = await buyer((variant, 1))
    code = await codes(value=1_000)
    await auth_client.post(
        f"{API}/cart/discount", json={"code": code.code}, headers=ready.account.headers
    )
    quote = await ready.quote()

    async def refuse(self: RedemptionService, **kwargs: Any) -> Any:
        raise discount_error(Rejection.EXHAUSTED)

    monkeypatch.setattr(RedemptionService, "redeem", refuse)
    _error(await ready.order(fingerprint=quote["fingerprint"]), 422, "DISCOUNT_NOT_APPLICABLE")

    assert await _orders_of(db_engine, ready.account.id) == []
    assert (
        await _count(
            db_engine, InventoryReservation, InventoryReservation.user_id == ready.account.id
        )
        == 0
    )
    async with AsyncSession(db_engine) as session:
        item = await session.get(InventoryItem, await _item_id(db_engine, variant.id))
    assert item is not None and item.reserved_quantity == 0


async def test_the_order_number_year_is_the_created_at_year(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0))
    for moment in (
        datetime(2026, 12, 31, 23, 59, 59, 999_999, tzinfo=UTC),
        datetime(2027, 1, 1, 0, 0, tzinfo=UTC),
    ):
        # A buyer each: the first order's reservation is still live at the second moment.
        ready = await buyer((variant, 1))
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            service = OrderService(session)
            async with session.begin():
                quote = await CheckoutService(session).build_quote(
                    ready.account.id,
                    UUID(ready.address_id),
                    ready.method.id,
                    now=moment,
                )
            placed = await service.place(
                ready.account.id,
                str(uuid4()),
                CreateOrderRequest(
                    address_id=UUID(ready.address_id),
                    shipping_method_id=ready.method.id,
                    fingerprint=quote.fingerprint,
                ),
                now=moment,
            )
        assert placed.body["order_number"].startswith(f"ORD-{moment.year}-")
        assert datetime.fromisoformat(placed.body["created_at"]) == moment


# --- concurrency and lock order (ADR-048) ------------------------------------------------


async def test_two_buyers_for_the_last_unit(catalog: Catalog, buyer: MakeBuyer) -> None:
    variant = await catalog.variant(await catalog.product(), stock=(1, 0, 0))
    first, second = await buyer((variant, 1)), await buyer((variant, 1))
    quotes = [await first.quote(), await second.quote()]

    responses = await asyncio.gather(
        first.order(fingerprint=quotes[0]["fingerprint"]),
        second.order(fingerprint=quotes[1]["fingerprint"]),
    )

    assert sorted(response.status_code for response in responses) == [201, 409]


async def test_the_same_key_three_times_places_one_order(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0))
    ready = await buyer((variant, 1))
    quote = await ready.quote()
    key = str(uuid4())

    responses = await asyncio.gather(*(ready.order(key, quote["fingerprint"]) for _ in range(3)))

    assert [response.status_code for response in responses] == [201, 201, 201]
    assert len({response.json()["id"] for response in responses}) == 1
    assert len(await _orders_of(db_engine, ready.account.id)) == 1


async def _with_code(auth_client: AsyncClient, ready: Buyer, code: DiscountCode) -> str:
    applied = await auth_client.post(
        f"{API}/cart/discount", json={"code": code.code}, headers=ready.account.headers
    )
    assert applied.status_code == 200, applied.text
    fingerprint: str = (await ready.quote())["fingerprint"]
    return fingerprint


async def test_buyers_sharing_a_code_do_not_deadlock(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, codes: Any
) -> None:
    variant = await catalog.variant(await catalog.product(), stock=(10, 0, 0))
    buyers = [await buyer((variant, 1)) for _ in range(3)]
    roomy = await codes(value=1_000, usage_limit_total=10)
    fingerprints = [await _with_code(auth_client, ready, roomy) for ready in buyers]

    responses = await asyncio.gather(
        *(ready.order(fingerprint=fp) for ready, fp in zip(buyers, fingerprints, strict=True))
    )

    assert [response.status_code for response in responses] == [201, 201, 201]


async def test_the_last_use_of_a_code_goes_to_one_buyer(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, codes: Any
) -> None:
    variant = await catalog.variant(await catalog.product(), stock=(10, 0, 0))
    first, second = await buyer((variant, 1)), await buyer((variant, 1))
    last = await codes(value=1_000, usage_limit_total=1)
    fingerprints = [await _with_code(auth_client, ready, last) for ready in (first, second)]

    responses = await asyncio.gather(
        first.order(fingerprint=fingerprints[0]), second.order(fingerprint=fingerprints[1])
    )

    assert sorted(response.status_code for response in responses) == [201, 422]


async def test_crossing_multi_variant_orders_do_not_deadlock(
    catalog: Catalog, buyer: MakeBuyer
) -> None:
    product = await catalog.product()
    a = await catalog.variant(product, stock=(5, 0, 0))
    b = await catalog.variant(product, stock=(5, 0, 0))
    first, second = await buyer((a, 1), (b, 1)), await buyer((b, 1), (a, 1))
    fps = [(await first.quote())["fingerprint"], (await second.quote())["fingerprint"]]

    responses = await asyncio.gather(
        first.order(fingerprint=fps[0]), second.order(fingerprint=fps[1])
    )

    assert [response.status_code for response in responses] == [201, 201]


async def test_orders_racing_an_admin_stock_adjustment(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, make_account: MakeAccount
) -> None:
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0))
    ready = await buyer((variant, 2))
    admin = await make_account("admin")
    fp = (await ready.quote())["fingerprint"]

    order, adjusted = await asyncio.gather(
        ready.order(fingerprint=fp),
        auth_client.patch(
            f"{API}/admin/inventory/{variant.id}",
            json={"adjustment_type": "increase", "quantity": 3, "reason": "restock"},
            headers=admin.headers,
        ),
    )

    assert (order.status_code, adjusted.status_code) == (201, 200), (order.text, adjusted.text)


async def test_orders_racing_an_admin_code_edit(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    codes: Any,
    make_account: MakeAccount,
) -> None:
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0))
    ready = await buyer((variant, 1))
    code = await codes(value=1_000, usage_limit_total=5)
    fp = await _with_code(auth_client, ready, code)
    admin = await make_account("admin")

    order, edited = await asyncio.gather(
        ready.order(fingerprint=fp),
        auth_client.patch(
            f"{API}/admin/discounts/{code.id}",
            json={"usage_limit_total": 6},
            headers=admin.headers,
        ),
    )

    # Either order: the edit does not change the price, so the order is placed.
    assert edited.status_code == 200, edited.text
    assert order.status_code == 201, order.text


async def test_orders_racing_the_expiry_sweep_and_a_release(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    codes: Any,
    db_engine: AsyncEngine,
) -> None:
    variant = await catalog.variant(await catalog.product(), stock=(2, 0, 0))
    code = await codes(value=1_000, usage_limit_total=5)
    old = await buyer((variant, 2))
    placed = await old.order(fingerprint=await _with_code(auth_client, old, code))
    assert placed.status_code == 201, placed.text
    old_id = UUID(placed.json()["id"])
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            update(InventoryReservation)
            .where(InventoryReservation.order_id == old_id)
            .values(expires_at=utc_now() - timedelta(seconds=1))
        )
    ready = await buyer((variant, 2))
    fp = await _with_code(auth_client, ready, code)

    # The old order's customer cancels while the job expires it (ORD-06: one of them wins).
    order, swept, cancelled = await asyncio.gather(
        ready.order(fingerprint=fp),
        sweep_expired_reservations(db_engine),
        old.client.post(f"{ORDERS}/{old_id}/cancel", headers=old.account.headers),
    )

    assert order.status_code == 201, order.text
    assert cancelled.status_code == 200, cancelled.text
    assert swept.failed == 0


async def test_a_user_without_a_valid_mobile_is_refused(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0))
    ready = await buyer((variant, 1))
    fp = (await ready.quote())["fingerprint"]
    original = AsyncSession.scalar

    async def no_phone(self: AsyncSession, statement: Any, *args: Any, **kwargs: Any) -> Any:
        if "users.phone" in str(statement):
            return None
        return await original(self, statement, *args, **kwargs)

    monkeypatch.setattr(AsyncSession, "scalar", no_phone)
    response = await ready.order(fingerprint=fp)
    monkeypatch.undo()
    _error(response, 401, "MOBILE_NOT_VERIFIED")
    assert await _orders_of(db_engine, ready.account.id) == []


async def test_orders_racing_a_cart_write(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer
) -> None:
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0))
    ready = await buyer((variant, 1))
    item_id = (await ready.quote())["items"][0]["id"]
    fp = (await ready.quote())["fingerprint"]

    order, written = await asyncio.gather(
        ready.order(fingerprint=fp),
        auth_client.patch(
            f"{API}/cart/items/{item_id}", json={"quantity": 2}, headers=ready.account.headers
        ),
    )

    # Serialized on the cart row: the order sees the old cart (201) or the new one (409).
    assert written.status_code == 200, written.text
    assert order.status_code in (201, 409), order.text
