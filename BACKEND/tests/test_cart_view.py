"""GET /cart and POST /cart/acknowledge-prices: server pricing, change flags (CART-03)."""

from __future__ import annotations

import asyncio
import random
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest_asyncio
from alembic.config import Config
from conftest import Catalog, MakeAccount, count_queries, nested_keys
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import delete, func, insert, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from alembic import command
from app.core.time import utc_now
from app.db.models import (
    Cart,
    CartItem,
    PricingSetting,
    Product,
    ProductVariant,
    User,
    UserStatus,
)
from app.modules.cart.tokens import CART_COOKIE_NAME
from app.modules.cart.view import price_cart_lines
from app.modules.pricing.calculator import LineInput, PricingPolicy, VariantPrice
from app.shared.money import RoundingMode

API = "/api/v1"
CART = f"{API}/cart"
ITEMS = f"{CART}/items"
ACK = f"{CART}/acknowledge-prices"
STOCK_KEYS = {"free", "available_quantity", "stock", "reserved", "max_quantity", "quantity_left"}


def _error(response: Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body: dict[str, Any] = response.json()["error"]
    assert body["code"] == code
    return body


async def _add(
    client: AsyncClient, headers: dict[str, str], variant: ProductVariant, quantity: int = 1
) -> str:
    response = await client.post(
        ITEMS, json={"variant_id": str(variant.id), "quantity": quantity}, headers=headers
    )
    assert response.status_code == 201, response.text
    line_id: str = response.json()["id"]
    return line_id


async def _cart(client: AsyncClient, headers: dict[str, str]) -> dict[str, Any]:
    response = await client.get(CART, headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body: dict[str, Any] = response.json()
    return body


def _line(cart: dict[str, Any], line_id: str) -> dict[str, Any]:
    lines: list[dict[str, Any]] = [item for item in cart["items"] if item["id"] == line_id]
    [line] = lines
    return line


@pytest_asyncio.fixture
async def restore_settings(db_engine: AsyncEngine) -> AsyncIterator[None]:
    async with AsyncSession(db_engine) as session:
        row = (await session.execute(select(PricingSetting.__table__))).mappings().one()
    original = dict(row)
    yield
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(PricingSetting))
        await session.execute(insert(PricingSetting).values(**original))


# --- ADR-031 ordering (no database) --------------------------------------------------


def test_shuffled_lines_price_identically() -> None:
    """ADR-031: lines go to the calculator by line id, whatever order they come in."""
    rng = random.Random(41)
    now = utc_now()
    policy = PricingPolicy(
        tax_enabled=True, tax_rate_bps=900, rounding_mode=RoundingMode.UP, rounding_step=100
    )
    for _ in range(50):
        lines = [
            LineInput(
                key=uuid4(),
                price=VariantPrice(
                    base_price=rng.randint(1, 99_999), tax_enabled=rng.random() < 0.5
                ),
                quantity=rng.randint(1, 4),
            )
            for _ in range(rng.randint(1, 6))
        ]
        base = price_cart_lines(lines, policy, now)
        again = price_cart_lines(rng.sample(lines, len(lines)), policy, now)
        assert again == base  # line splits, totals and fingerprint


# --- reading -------------------------------------------------------------------------


async def test_empty_carts(
    auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
) -> None:
    customer = await make_account("customer")
    auth_client.cookies.clear()

    for headers in ({}, customer.headers):
        response = await auth_client.get(CART, headers=headers)
        assert response.status_code == 200, response.text
        assert "set-cookie" not in response.headers
        body = response.json()
        assert body["items"] == [] and body["grand_total"] == 0 and body["has_changes"] is False
    async with AsyncSession(db_engine) as session:
        carts = await session.scalar(
            select(func.count()).select_from(Cart).where(Cart.user_id == customer.id)
        )
    assert carts == 0


async def test_cart_is_priced_by_the_server(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog
) -> None:
    customer = await make_account("customer")
    product = await catalog.product(title="Pearl ring")
    on_sale = await catalog.variant(
        product,
        stock=(5, 0, 0),
        options={"color": "Gold"},
        base_price=10_000,
        sale_price=8_000,
        sale_start_at=utc_now() - timedelta(days=1),
    )
    plain = await catalog.variant(product, stock=(5, 0, 0), base_price=3_000)
    first = await _add(auth_client, customer.headers, on_sale, 2)
    second = await _add(auth_client, customer.headers, plain, 1)

    cart = await _cart(auth_client, customer.headers)

    sale_line, plain_line = _line(cart, first), _line(cart, second)
    assert sale_line["unit_price"] == {"original": 10_000, "final": 8_000}
    assert (sale_line["subtotal"], sale_line["product_discount"], sale_line["total"]) == (
        20_000,
        4_000,
        16_000,
    )
    assert (sale_line["product_title"], sale_line["options"]) == ("Pearl ring", {"color": "Gold"})
    assert sale_line["sku"] == on_sale.sku and sale_line["product_slug"] == product.slug
    assert plain_line["total"] == 3_000
    assert (cart["subtotal"], cart["product_discount_total"], cart["grand_total"]) == (
        23_000,
        4_000,
        19_000,
    )
    assert (cart["shipping_amount"], cart["currency"]) == (0, "TOMAN")
    assert all(line["stock_status"] == "ok" and not line["price_changed"] for line in cart["items"])
    assert not nested_keys(cart) & STOCK_KEYS
    # One source of truth: the same final price as the public pricing endpoint.
    pricing = (await auth_client.get(f"{API}/products/{product.id}/pricing")).json()
    finals = {item["variant_id"]: item["price"]["final_price"] for item in pricing["variants"]}
    assert finals[str(on_sale.id)] == 8_000 and finals[str(plain.id)] == 3_000


async def test_stock_flags_never_show_numbers(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog
) -> None:
    customer = await make_account("customer")
    product = await catalog.product()
    short = await catalog.variant(product, stock=(3, 0, 0))
    gone = await catalog.variant(product, stock=(2, 0, 0))
    short_line = await _add(auth_client, customer.headers, short, 3)
    gone_line = await _add(auth_client, customer.headers, gone, 2)
    async with AsyncSession(catalog.engine) as session, session.begin():
        await session.execute(
            text("UPDATE inventory_items SET total_quantity = 1 WHERE variant_id = :v"),
            {"v": short.id},
        )
        await session.execute(
            text("UPDATE inventory_items SET total_quantity = 0 WHERE variant_id = :v"),
            {"v": gone.id},
        )

    cart = await _cart(auth_client, customer.headers)

    assert _line(cart, short_line)["stock_status"] == "insufficient"
    assert _line(cart, gone_line)["stock_status"] == "out_of_stock"
    # Short lines are still priced; ordering rejects them later.
    assert _line(cart, gone_line)["total"] is not None
    assert cart["has_changes"] is True
    assert not nested_keys(cart) & STOCK_KEYS


async def test_unavailable_lines_are_flagged_not_priced(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog
) -> None:
    customer = await make_account("customer")
    product = await catalog.product()
    other_product = await catalog.product()
    draft_product = await catalog.product()
    kept = await catalog.variant(product, stock=(5, 0, 0), base_price=1_000)
    deleted = await catalog.variant(product, stock=(5, 0, 0))
    unpriced = await catalog.variant(product, stock=(5, 0, 0))
    unsellable = await catalog.variant(product, stock=(5, 0, 0))
    of_hidden = await catalog.variant(other_product, stock=(5, 0, 0))
    of_draft = await catalog.variant(draft_product, stock=(5, 0, 0), base_price=2_000)
    lines = {
        variant.id: await _add(auth_client, customer.headers, variant)
        for variant in (kept, deleted, unpriced, unsellable, of_hidden, of_draft)
    }
    await catalog.set(ProductVariant, deleted.id, deleted_at=utc_now())
    await catalog.set(ProductVariant, unpriced.id, is_active=False, base_price=None)
    await catalog.set(ProductVariant, unsellable.id, is_purchasable=False)
    await catalog.set(Product, other_product.id, deleted_at=utc_now())
    await catalog.set(Product, draft_product.id, status="draft", published_at=None)
    # A price change on a line that cannot be bought is not flagged.
    await catalog.set(ProductVariant, of_draft.id, base_price=2_500, price_version=1)

    cart = await _cart(auth_client, customer.headers)

    for variant_id, line_id in lines.items():
        line = _line(cart, line_id)
        expected = variant_id == kept.id
        assert line["available"] is expected
        if not expected:
            assert (line["total"], line["unit_price"], line["stock_status"]) == (None, None, None)
            assert (line["price_changed"], line["previous_unit_price"]) == (False, None)
    assert cart["grand_total"] == 1_000


async def test_read_has_no_n_plus_one(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog
) -> None:
    customer = await make_account("customer")
    product = await catalog.product()
    variants = [await catalog.variant(product, stock=(5, 0, 0)) for _ in range(6)]
    await _add(auth_client, customer.headers, variants[0])
    with count_queries(auth_client) as one:
        await _cart(auth_client, customer.headers)
    for variant in variants[1:]:
        await _add(auth_client, customer.headers, variant)
    with count_queries(auth_client) as six:
        await _cart(auth_client, customer.headers)

    assert len(six) == len(one)


# --- price change flag (ADR-041) -----------------------------------------------------


async def test_price_change_is_flagged_until_acknowledged(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog
) -> None:
    customer = await make_account("customer")
    product = await catalog.product()
    first = await catalog.variant(product, stock=(5, 0, 0), base_price=5_000)
    second = await catalog.variant(product, stock=(5, 0, 0), base_price=7_000)
    first_line = await _add(auth_client, customer.headers, first)
    second_line = await _add(auth_client, customer.headers, second)
    await catalog.set(ProductVariant, first.id, base_price=5_500, price_version=1)
    await catalog.set(ProductVariant, second.id, base_price=6_000, price_version=1)

    cart = await _cart(auth_client, customer.headers)
    changed = _line(cart, first_line)
    assert (changed["price_changed"], changed["previous_unit_price"]) == (True, 5_000)
    assert changed["unit_price"]["final"] == 5_500
    assert cart["has_changes"] is True

    # Any write to a line moves only that line's baseline.
    patched = await auth_client.patch(
        f"{ITEMS}/{first_line}", json={"quantity": 2}, headers=customer.headers
    )
    assert patched.status_code == 200
    cart = await _cart(auth_client, customer.headers)
    assert _line(cart, first_line)["price_changed"] is False
    assert _line(cart, first_line)["previous_unit_price"] is None
    assert _line(cart, second_line)["price_changed"] is True

    acknowledged = await auth_client.post(ACK, headers=customer.headers)
    assert acknowledged.status_code == 200, acknowledged.text
    assert acknowledged.headers["cache-control"] == "no-store"
    assert all(not line["price_changed"] for line in acknowledged.json()["items"])
    cart = await _cart(auth_client, customer.headers)
    assert cart["has_changes"] is False


async def test_flag_follows_the_final_price_not_the_version(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog
) -> None:
    customer = await make_account("customer")
    product = await catalog.product()
    now = utc_now()
    variant = await catalog.variant(
        product,
        stock=(5, 0, 0),
        base_price=9_000,
        sale_price=6_000,
        sale_start_at=now - timedelta(days=1),
    )
    line_id = await _add(auth_client, customer.headers, variant)

    # A version bump with the same final price is not a change.
    await catalog.set(ProductVariant, variant.id, price_version=5)
    assert _line(await _cart(auth_client, customer.headers), line_id)["price_changed"] is False

    # The sale ends on its own clock (no version bump): flagged.
    await catalog.set(ProductVariant, variant.id, sale_end_at=now)
    line = _line(await _cart(auth_client, customer.headers), line_id)
    assert (line["price_changed"], line["previous_unit_price"]) == (True, 6_000)

    # Back to the seen price: the flag clears by itself.
    await catalog.set(ProductVariant, variant.id, sale_end_at=None)
    assert _line(await _cart(auth_client, customer.headers), line_id)["price_changed"] is False


async def test_decrease_on_an_unpriced_variant_keeps_the_baseline(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog, db_engine: AsyncEngine
) -> None:
    customer = await make_account("customer")
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0), base_price=4_000)
    line_id = await _add(auth_client, customer.headers, variant, 3)
    await catalog.set(ProductVariant, variant.id, is_active=False, base_price=None)

    shrink = await auth_client.patch(
        f"{ITEMS}/{line_id}", json={"quantity": 1}, headers=customer.headers
    )
    acknowledged = await auth_client.post(ACK, headers=customer.headers)

    assert shrink.status_code == 200 and acknowledged.status_code == 200
    async with AsyncSession(db_engine) as session:
        line = await session.get(CartItem, UUID(line_id))
    assert line is not None and (line.quantity, line.seen_unit_price) == (1, 4_000)
    assert _line(acknowledged.json(), line_id)["available"] is False


async def test_missing_settings_row_is_500_only_for_a_priced_cart(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    catalog: Catalog,
    db_engine: AsyncEngine,
    restore_settings: None,
) -> None:
    customer, empty = await make_account("customer"), await make_account("customer")
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0))
    await _add(auth_client, customer.headers, variant)
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(PricingSetting))

    app = auth_client._transport.app  # type: ignore[attr-defined]
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        assert (await client.get(CART, headers=empty.headers)).status_code == 200
        _error(await client.get(CART, headers=customer.headers), 500, "INTERNAL_SERVER_ERROR")


# --- identity ------------------------------------------------------------------------


async def test_identity_and_ownership(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog
) -> None:
    owner = await make_account("customer")
    other = await make_account("customer")
    blocked = await make_account("customer")
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0))
    await _add(auth_client, owner.headers, variant)
    await catalog.set(User, blocked.id, status=UserStatus.BLOCKED)

    assert (await _cart(auth_client, other.headers))["items"] == []
    _error(await auth_client.get(CART, headers=blocked.headers), 403, "FORBIDDEN")
    _error(await auth_client.post(ACK, headers=blocked.headers), 403, "FORBIDDEN")
    bad = {"Authorization": "Bearer nope"}
    _error(await auth_client.get(CART, headers=bad), 401, "UNAUTHORIZED")
    _error(await auth_client.post(ACK, headers=bad), 401, "UNAUTHORIZED")
    response = await auth_client.get(CART, params={"x": "1"}, headers=owner.headers)
    _error(response, 400, "VALIDATION_ERROR")


async def test_guest_reads_and_acknowledges_through_the_cookie(
    auth_client: AsyncClient, catalog: Catalog, db_engine: AsyncEngine
) -> None:
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0), base_price=2_000)
    auth_client.cookies.clear()
    created = await auth_client.post(ITEMS, json={"variant_id": str(variant.id), "quantity": 1})
    token = created.cookies[CART_COOKIE_NAME]
    try:
        await catalog.set(ProductVariant, variant.id, base_price=2_500)
        auth_client.cookies.set(CART_COOKIE_NAME, token)
        assert (await _cart(auth_client, {}))["items"][0]["price_changed"] is True
        acknowledged = await auth_client.post(ACK)
        assert acknowledged.status_code == 200
        assert acknowledged.cookies[CART_COOKIE_NAME] == token  # sliding expiry renewed
        assert not acknowledged.json()["items"][0]["price_changed"]

        # No cookie (as from a cross-site form, SameSite=Lax): nothing to read or change.
        auth_client.cookies.clear()
        for response in (await auth_client.get(CART), await auth_client.post(ACK)):
            assert response.status_code == 200 and response.json()["items"] == []
            assert "set-cookie" not in response.headers
    finally:
        async with AsyncSession(db_engine) as session, session.begin():
            await session.execute(
                delete(Cart).where(
                    Cart.id.in_(select(CartItem.cart_id).where(CartItem.variant_id == variant.id))
                )
            )


# --- migration -----------------------------------------------------------------------


async def _alembic(database_url: str, action: str, revision: str) -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    await asyncio.to_thread(getattr(command, action), config, revision)


async def test_migration_backfills_the_baseline(
    db_engine: AsyncEngine, migrated_database: str, catalog: Catalog, make_account: MakeAccount
) -> None:
    customer = await make_account("customer")
    product = await catalog.product()
    now = utc_now()
    on_sale = await catalog.variant(
        product, base_price=9_000, sale_price=7_000, sale_start_at=now - timedelta(days=1)
    )
    ended = await catalog.variant(
        product, base_price=9_000, sale_price=7_000, sale_end_at=now - timedelta(days=1)
    )
    unpriced = await catalog.variant(product, base_price=None, is_active=False, price_version=3)
    try:
        await _alembic(migrated_database, "downgrade", "20261012_0017")
        async with AsyncSession(db_engine) as session, session.begin():
            cart_id = await session.scalar(
                text("INSERT INTO carts (user_id) VALUES (:u) RETURNING id"), {"u": customer.id}
            )
            for variant in (on_sale, ended, unpriced):
                await session.execute(
                    text(
                        "INSERT INTO cart_items (cart_id, product_id, variant_id, quantity)"
                        " VALUES (:c, :p, :v, 1)"
                    ),
                    {"c": cart_id, "p": product.id, "v": variant.id},
                )
        await _alembic(migrated_database, "upgrade", "head")
    finally:
        await _alembic(migrated_database, "upgrade", "head")

    async with AsyncSession(db_engine) as session:
        rows = await session.execute(
            select(CartItem.variant_id, CartItem.seen_unit_price, CartItem.seen_price_version)
        )
        seen = {variant_id: (price, version) for variant_id, price, version in rows}
    assert seen[on_sale.id] == (7_000, 0)
    assert seen[ended.id] == (9_000, 0)
    assert seen[unpriced.id] == (0, 3)


async def test_acknowledge_has_no_n_plus_one(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog
) -> None:
    customer = await make_account("customer")
    product = await catalog.product()
    variants = [await catalog.variant(product, stock=(5, 0, 0)) for _ in range(6)]
    await _add(auth_client, customer.headers, variants[0])
    with count_queries(auth_client) as one:
        assert (await auth_client.post(ACK, headers=customer.headers)).status_code == 200
    for variant in variants[1:]:
        await _add(auth_client, customer.headers, variant)
    with count_queries(auth_client) as six:
        assert (await auth_client.post(ACK, headers=customer.headers)).status_code == 200

    assert len(six) == len(one)
