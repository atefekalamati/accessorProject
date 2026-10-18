"""POST /checkout/validate: the re-checked quote and its fingerprint (ORD-03, ADR-047)."""

from __future__ import annotations

import random
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from conftest import Account, Catalog, MakeAccount
from httpx import AsyncClient, Response
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.time import utc_now
from app.db.models import (
    Address,
    DiscountAttempt,
    DiscountCode,
    DiscountType,
    InventoryItem,
    InventoryReservation,
    InventoryReservationItem,
    PricingSetting,
    ProductVariant,
    ShippingMethod,
)
from app.modules.cart.view import price_cart_lines
from app.modules.checkout.quote import QuotedCode, QuotedShipping, quote_fingerprint
from app.modules.discounts.rules import CodeRules
from app.modules.pricing.calculator import CodeDiscount, LineInput, PricingPolicy, VariantPrice
from app.modules.shipping.calculator import ShippingRates
from app.shared.money import RoundingMode

API = "/api/v1"
URL = f"{API}/checkout/validate"
ITEMS = f"{API}/cart/items"
ADDRESS: dict[str, Any] = {
    "recipient_name": "Sara Ahmadi",
    "phone": "09121234567",
    "province": "Tehran",
    "city": "Tehran",
    "postal_code": "1234567890",
    "address_line": "Valiasr St, No. 10",
}

# --- pure: stable order and fingerprint coverage -------------------------------------

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
POLICY = PricingPolicy(
    tax_enabled=True, tax_rate_bps=900, rounding_mode=RoundingMode.NEAREST, rounding_step=10
)
RULES = CodeRules(
    type=DiscountType.PERCENT,
    value=1_250,
    max_amount=None,
    min_order_amount=None,
    starts_at=None,
    ends_at=None,
    usage_limit_total=None,
    usage_limit_per_user=None,
    is_active=True,
    deleted=False,
)


def _lines(count: int = 7) -> list[LineInput]:
    rng = random.Random(31)
    return [
        LineInput(
            key=UUID(int=index + 1),
            price=VariantPrice(base_price=rng.randrange(1_000, 90_000), tax_enabled=index % 2 == 0),
            quantity=rng.randrange(1, 4),
        )
        for index in range(count)
    ]


def _fingerprint(lines: list[LineInput], **changes: Any) -> str:
    pricing = price_cart_lines(
        lines,
        changes.get("policy", POLICY),
        NOW,
        CodeDiscount(percent_bps=1_250),
        shipping=changes.get("shipping", 30_000),
    )
    return quote_fingerprint(
        pricing,
        QuotedCode(changes.get("code_id", UUID(int=99)), changes.get("rules", RULES)),
        QuotedShipping(
            changes.get("method_id", UUID(int=7)),
            changes.get("rates", ShippingRates(30_000, 500_000)),
        ),
        [(str(line.key), line.quantity) for line in lines],
    )


def test_shuffled_lines_give_the_same_pricing_and_fingerprint() -> None:
    lines = _lines()
    base = price_cart_lines(lines, POLICY, NOW, shipping=30_000)
    for seed in range(20):
        shuffled = list(lines)
        random.Random(seed).shuffle(shuffled)
        again = price_cart_lines(shuffled, POLICY, NOW, shipping=30_000)
        assert again.lines == base.lines and again.fingerprint == base.fingerprint
        assert _fingerprint(shuffled) == _fingerprint(lines)


def test_every_part_of_the_quote_changes_the_fingerprint() -> None:
    lines = _lines()
    base = _fingerprint(lines)
    more = [*lines[:-1], LineInput(lines[-1].key, lines[-1].price, lines[-1].quantity + 1)]
    repriced = [
        *lines[:-1],
        LineInput(
            lines[-1].key,
            VariantPrice(base_price=(lines[-1].price.base_price or 0) + 1, price_version=1),
            lines[-1].quantity,
        ),
    ]
    variants = [
        _fingerprint(more),
        _fingerprint(repriced),
        _fingerprint(lines, policy=replace(POLICY, version=2)),
        _fingerprint(lines, code_id=UUID(int=98)),
        _fingerprint(lines, rules=replace(RULES, value=1_300)),
        _fingerprint(lines, method_id=UUID(int=8)),
        # Free shipping (amount 0) still covers the method's cost and threshold.
        _fingerprint(lines, shipping=0, rates=ShippingRates(30_000, 100)),
        _fingerprint(lines, shipping=0, rates=ShippingRates(31_000, 100)),
        _fingerprint(lines, rates=ShippingRates(30_000, 600_000)),
        _fingerprint(lines, shipping=31_000, rates=ShippingRates(31_000, 500_000)),
    ]
    assert len({base, *variants}) == len(variants) + 1


# --- the endpoint (integration) ------------------------------------------------------


@pytest_asyncio.fixture
async def methods(
    db_engine: AsyncEngine,
) -> AsyncIterator[Callable[..., Awaitable[ShippingMethod]]]:
    ids: list[UUID] = []

    async def make(**values: Any) -> ShippingMethod:
        method = ShippingMethod(**({"title": f"Post {uuid4().hex[:6]}", "cost": 30_000} | values))
        async with AsyncSession(db_engine, expire_on_commit=False) as session, session.begin():
            session.add(method)
        ids.append(method.id)
        return method

    yield make
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(ShippingMethod).where(ShippingMethod.id.in_(ids)))


@pytest_asyncio.fixture
async def codes(db_engine: AsyncEngine) -> AsyncIterator[Callable[..., Awaitable[DiscountCode]]]:
    ids: list[UUID] = []

    async def make(**values: Any) -> DiscountCode:
        base: dict[str, Any] = {"code": f"Q{uuid4().hex[:10].upper()}", "type": "fixed"}
        code = DiscountCode(**(base | values))
        async with AsyncSession(db_engine, expire_on_commit=False) as session, session.begin():
            session.add(code)
        ids.append(code.id)
        return code

    yield make
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(DiscountAttempt))
        await session.execute(delete(DiscountCode).where(DiscountCode.id.in_(ids)))


@pytest_asyncio.fixture
async def shopper(
    catalog: Catalog, make_account: MakeAccount, db_engine: AsyncEngine
) -> AsyncIterator[Callable[..., Awaitable[Account]]]:
    """A customer; their addresses go before the users (addresses.user_id is RESTRICT)."""
    users: list[UUID] = []

    async def make() -> Account:
        account = await make_account("customer")
        users.append(account.id)
        return account

    yield make
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(Address).where(Address.user_id.in_(users)))


async def _address(client: AsyncClient, account: Account) -> str:
    response = await client.post(f"{API}/addresses", json=ADDRESS, headers=account.headers)
    assert response.status_code == 201, response.text
    address_id: str = response.json()["id"]
    return address_id


async def _add(
    client: AsyncClient, account: Account, variant: ProductVariant, quantity: int
) -> str:
    response = await client.post(
        ITEMS, json={"variant_id": str(variant.id), "quantity": quantity}, headers=account.headers
    )
    assert response.status_code in (200, 201), response.text
    item_id: str = response.json()["id"]
    return item_id


async def _validate(
    client: AsyncClient, account: Account, address_id: str, method_id: UUID
) -> Response:
    return await client.post(
        URL,
        json={"address_id": address_id, "shipping_method_id": str(method_id)},
        headers=account.headers,
    )


def _error(response: Response, status: int, code: str, kind: str | None = None) -> None:
    assert response.status_code == status, response.text
    body = response.json()["error"]
    assert body["code"] == code
    if kind is not None:
        assert body["details"][0]["type"] == kind


@pytest.mark.integration
async def test_quote_prices_the_cart_with_shipping(
    auth_client: AsyncClient, catalog: Catalog, shopper: Any, methods: Any
) -> None:
    account = await shopper()
    product = await catalog.product()
    first = await catalog.variant(product, stock=(10, 0, 0), base_price=100_000)
    second = await catalog.variant(
        product, stock=(10, 0, 0), base_price=50_000, options={"size": "M"}
    )
    await _add(auth_client, account, first, 1)
    await _add(auth_client, account, second, 2)
    address_id = await _address(auth_client, account)
    method = await methods(cost=35_000, free_shipping_threshold=10_000_000)

    response = await _validate(auth_client, account, address_id, method.id)
    again = await _validate(auth_client, account, address_id, method.id)

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert len(body["items"]) == 2 and body["subtotal"] == 200_000
    assert body["shipping"] == {
        "method_id": str(method.id),
        "title": method.title,
        "cost": 35_000,
        "free_shipping_threshold": 10_000_000,
        "amount": 35_000,
    }
    assert body["grand_total"] == (
        body["subtotal"]
        - body["product_discount_total"]
        - body["discount_code_amount"]
        + body["tax_amount"]
        + body["shipping_amount"]
    )
    assert body["discount"] is None and body["address_id"] == address_id
    assert [item["id"] for item in body["items"]] == sorted(item["id"] for item in body["items"])
    sized = next(item for item in body["items"] if item["variant_id"] == str(second.id))
    assert sized["options"] == {"size": "M"} and sized["quantity"] == 2
    assert len(body["fingerprint"]) == 64
    assert again.json()["fingerprint"] == body["fingerprint"]


@pytest.mark.integration
async def test_a_code_can_cost_the_free_shipping_and_changes_the_fingerprint(
    auth_client: AsyncClient,
    catalog: Catalog,
    shopper: Any,
    methods: Any,
    codes: Any,
    db_engine: AsyncEngine,
) -> None:
    account = await shopper()
    variant = await catalog.variant(await catalog.product(), stock=(10, 0, 0), base_price=100_000)
    await _add(auth_client, account, variant, 2)
    address_id = await _address(auth_client, account)
    method = await methods(cost=30_000, free_shipping_threshold=180_000)

    free = (await _validate(auth_client, account, address_id, method.id)).json()
    code = await codes(value=30_000)
    applied = await auth_client.post(
        f"{API}/cart/discount", json={"code": code.code}, headers=account.headers
    )
    assert applied.status_code == 200, applied.text
    charged = (await _validate(auth_client, account, address_id, method.id)).json()

    assert free["shipping_amount"] == 0
    # 200 000 − 30 000 = 170 000 is below the threshold: shipping is charged (D34).
    assert (charged["discount_code_amount"], charged["shipping_amount"]) == (30_000, 30_000)
    assert charged["discount"] == {"code": code.code, "amount": 30_000}
    assert charged["fingerprint"] != free["fingerprint"]

    # The code stops applying: 422 with its reason, not a quote without it.
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            update(DiscountCode).where(DiscountCode.id == code.id).values(is_active=False)
        )
    _error(
        await _validate(auth_client, account, address_id, method.id),
        422,
        "DISCOUNT_NOT_APPLICABLE",
        "invalid",
    )


@pytest.mark.integration
async def test_changes_after_a_quote_change_the_fingerprint(
    auth_client: AsyncClient, catalog: Catalog, shopper: Any, methods: Any, db_engine: AsyncEngine
) -> None:
    account = await shopper()
    variant = await catalog.variant(await catalog.product(), stock=(10, 0, 0), base_price=100_000)
    item_id = await _add(auth_client, account, variant, 1)
    address_id = await _address(auth_client, account)
    method = await methods(cost=30_000)

    async def fingerprint() -> str:
        response = await _validate(auth_client, account, address_id, method.id)
        assert response.status_code == 200, response.text
        value: str = response.json()["fingerprint"]
        return value

    seen = [await fingerprint()]
    await auth_client.patch(f"{ITEMS}/{item_id}", json={"quantity": 2}, headers=account.headers)
    seen.append(await fingerprint())
    await catalog.set(ProductVariant, variant.id, base_price=110_000, price_version=5)
    seen.append(await fingerprint())
    await catalog.set(ShippingMethod, method.id, cost=31_000)
    seen.append(await fingerprint())
    await catalog.set(ShippingMethod, method.id, free_shipping_threshold=900_000_000)
    seen.append(await fingerprint())
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(update(PricingSetting).values(version=PricingSetting.version + 1))
    try:
        seen.append(await fingerprint())
    finally:
        # The settings row is shared by the whole test database.
        async with AsyncSession(db_engine) as session, session.begin():
            await session.execute(update(PricingSetting).values(version=PricingSetting.version - 1))
    assert len(set(seen)) == len(seen)


@pytest.mark.integration
async def test_errors_in_check_order(
    auth_client: AsyncClient, catalog: Catalog, shopper: Any, methods: Any, db_engine: AsyncEngine
) -> None:
    account, other = await shopper(), await shopper()
    method = await methods()
    inactive = await methods(is_active=False)
    address_id = await _address(auth_client, account)
    others_address = await _address(auth_client, other)

    _error(
        await _validate(auth_client, account, address_id, method.id),
        422,
        "BUSINESS_RULE_VIOLATION",
        "cart_empty",
    )

    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0))
    await _add(auth_client, account, variant, 2)
    _error(await _validate(auth_client, account, others_address, method.id), 404, "NOT_FOUND")
    _error(await _validate(auth_client, account, str(uuid4()), method.id), 404, "NOT_FOUND")
    for method_id in (inactive.id, uuid4()):
        _error(
            await _validate(auth_client, account, address_id, method_id),
            422,
            "BUSINESS_RULE_VIOLATION",
            "shipping_method_unavailable",
        )

    # Only one unit is free now (another order holds three): 409 with the variant.
    await catalog.set(InventoryItem, (await _item_id(db_engine, variant.id)), reserved_quantity=4)
    short = await _validate(auth_client, account, address_id, method.id)
    _error(short, 409, "INSUFFICIENT_STOCK", "insufficient_stock")
    assert short.json()["error"]["details"][0]["variant_id"] == str(variant.id)

    # A soft-deleted variant is rejected (SD rule), before the stock check.
    await catalog.set(ProductVariant, variant.id, deleted_at=utc_now())
    gone = await _validate(auth_client, account, address_id, method.id)
    _error(gone, 422, "BUSINESS_RULE_VIOLATION", "line_unavailable")


@pytest.mark.integration
async def test_only_unavailable_lines_are_listed_and_expired_holds_are_free(
    auth_client: AsyncClient, catalog: Catalog, shopper: Any, methods: Any, db_engine: AsyncEngine
) -> None:
    account = await shopper()
    method = await methods()
    address_id = await _address(auth_client, account)
    kept = await catalog.variant(await catalog.product(), stock=(2, 0, 0))
    hidden_product = await catalog.product()
    hidden = await catalog.variant(hidden_product, stock=(2, 0, 0))
    await _add(auth_client, account, kept, 2)
    hidden_item = await _add(auth_client, account, hidden, 1)

    await catalog.set(type(hidden_product), hidden_product.id, deleted_at=utc_now())
    response = await _validate(auth_client, account, address_id, method.id)
    _error(response, 422, "BUSINESS_RULE_VIOLATION", "line_unavailable")
    assert [detail["item_id"] for detail in response.json()["error"]["details"]] == [hidden_item]

    # Both units of ``kept`` are held by an expired, unswept reservation: still free.
    await auth_client.delete(f"{ITEMS}/{hidden_item}", headers=account.headers)
    held = await _hold(db_engine, kept.id, quantity=2)
    try:
        ok = await _validate(auth_client, account, address_id, method.id)
        assert ok.status_code == 200, ok.text
    finally:
        await _drop_hold(db_engine, held)


async def _hold(engine: AsyncEngine, variant_id: UUID, quantity: int) -> UUID:
    """An active reservation already past its expiry, holding ``quantity`` units."""
    item_id = await _item_id(engine, variant_id)
    async with AsyncSession(engine, expire_on_commit=False) as session, session.begin():
        reservation = InventoryReservation(expires_at=utc_now() - timedelta(minutes=1))
        session.add(reservation)
        await session.flush()
        session.add(
            InventoryReservationItem(
                reservation_id=reservation.id,
                inventory_item_id=item_id,
                variant_id=variant_id,
                product_id=await session.scalar(
                    select(ProductVariant.product_id).where(ProductVariant.id == variant_id)
                ),
                quantity=quantity,
            )
        )
        await session.execute(
            update(InventoryItem)
            .where(InventoryItem.id == item_id)
            .values(reserved_quantity=InventoryItem.reserved_quantity + quantity)
        )
    return reservation.id


async def _drop_hold(engine: AsyncEngine, reservation_id: UUID) -> None:
    async with AsyncSession(engine) as session, session.begin():
        await session.execute(
            delete(InventoryReservationItem).where(
                InventoryReservationItem.reservation_id == reservation_id
            )
        )
        await session.execute(
            delete(InventoryReservation).where(InventoryReservation.id == reservation_id)
        )


async def _item_id(engine: AsyncEngine, variant_id: UUID) -> UUID:
    async with AsyncSession(engine) as session:
        found: UUID = (
            await session.scalars(
                select(InventoryItem.id).where(InventoryItem.variant_id == variant_id)
            )
        ).one()
        return found


@pytest.mark.integration
async def test_bad_requests_and_authentication(
    auth_client: AsyncClient, shopper: Any, methods: Any
) -> None:
    method = await methods()
    body = {"address_id": str(uuid4()), "shipping_method_id": str(method.id)}
    _error(await auth_client.post(URL, json=body), 401, "UNAUTHORIZED")
    _error(await auth_client.post(URL, json={"grand_total": 1}), 401, "UNAUTHORIZED")
    account = await shopper()
    for bad in (
        {},
        {"address_id": "x", "shipping_method_id": str(method.id)},
        body | {"grand_total": 1},
        body | {"shipping_amount": 0},
    ):
        _error(
            await auth_client.post(URL, json=bad, headers=account.headers), 400, "VALIDATION_ERROR"
        )
    _error(
        await auth_client.post(URL, json=body, params={"x": 1}, headers=account.headers),
        400,
        "VALIDATION_ERROR",
    )


@pytest.mark.integration
async def test_a_guest_cart_is_never_used(
    auth_client: AsyncClient, catalog: Catalog, shopper: Any, methods: Any
) -> None:
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0))
    guest = await auth_client.post(ITEMS, json={"variant_id": str(variant.id), "quantity": 1})
    assert guest.status_code in (200, 201), guest.text
    account = await shopper()
    address_id = await _address(auth_client, account)
    method = await methods()
    # The client still holds the guest cookie; only the user's own cart counts.
    _error(
        await _validate(auth_client, account, address_id, method.id),
        422,
        "BUSINESS_RULE_VIOLATION",
        "cart_empty",
    )
