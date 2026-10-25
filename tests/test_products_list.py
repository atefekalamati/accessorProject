from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from conftest import (
    INTERNAL_FIELDS,
    Catalog,
    MakeOrder,
    count_queries,
    nested_keys,
    unique_slug,
)
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.time import utc_now
from app.db.models import Category, OrderItem, Product, ProductStatus, ProductVariant
from app.modules.catalog.router import MAX_FILTER_VALUES

pytestmark = pytest.mark.integration

PRODUCTS = "/api/v1/products"
CARD_KEYS = {
    "id",
    "slug",
    "title",
    "published_at",
    "image_url",
    "price",
    "price_range",
    "max_discount_percent",
    "availability",
    "quick_add_variant_id",
}


def _url(category: Category) -> str:
    return f"/api/v1/categories/{category.slug}/products"


async def _list(client: AsyncClient, category: Category, **params: Any) -> Response:
    return await client.get(_url(category), params=params)


def _ids(response: Response) -> list[str]:
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()["items"]]


async def _priced(catalog: Catalog, category: Category, price: int, **fields: Any) -> Product:
    product = await catalog.product(category=category.id, **fields)
    await catalog.variant(product, base_price=price, stock=(5, 0, 0))
    return product


# --- contract ------------------------------------------------------------------------


async def test_card_contract(auth_client: AsyncClient, catalog: Catalog) -> None:
    category = await catalog.category()
    product = await catalog.product(category=category.id)
    now = utc_now()
    await catalog.variant(
        product,
        base_price=200_000,
        sale_price=150_000,
        sale_start_at=now - timedelta(days=1),
        stock=(3, 0, 0),
        display_order=1,
    )
    await catalog.variant(product, base_price=180_000, stock=(0, 0, 0), display_order=0)
    await catalog.image(product, is_main=True)

    response = await _list(auth_client, category)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert {key: body[key] for key in ("total", "page", "limit", "pages")} == {
        "total": 1,
        "page": 1,
        "limit": 24,
        "pages": 1,
    }
    [card] = body["items"]
    assert set(card) == CARD_KEYS
    assert not nested_keys(body["items"]) & INTERNAL_FIELDS
    assert card["id"] == str(product.id)
    assert card["slug"] == product.slug
    assert card["price"] == {
        "base_price": 200_000,
        "sale_price": 150_000,
        "final_price": 150_000,
        "discount_amount": 50_000,
        "discount_percent": 25,
    }
    assert card["price_range"] == {"min": 150_000, "max": 180_000}
    assert card["max_discount_percent"] == 25
    assert card["availability"] == "in_stock"
    # Two variants: the client must pick one on the product page.
    assert card["quick_add_variant_id"] is None
    assert card["image_url"] is not None and card["image_url"].endswith(".webp")


async def test_quick_add_only_for_a_single_purchasable_variant(
    auth_client: AsyncClient, catalog: Catalog
) -> None:
    category = await catalog.category()
    simple = await catalog.product(category=category.id, title="Simple")
    variant = await catalog.variant(simple, stock=(2, 0, 0))
    sold_out = await catalog.product(category=category.id, title="Sold out")
    await catalog.variant(sold_out, stock=(2, 2, 0))
    blocked = await catalog.product(category=category.id, title="Blocked")
    await catalog.variant(blocked, stock=(2, 0, 0), is_purchasable=False)

    response = await _list(auth_client, category, sort="newest")

    cards = {item["title"]: item for item in response.json()["items"]}
    assert cards["Simple"]["quick_add_variant_id"] == str(variant.id)
    assert cards["Sold out"]["quick_add_variant_id"] is None
    assert cards["Sold out"]["availability"] == "out_of_stock"
    assert cards["Blocked"]["quick_add_variant_id"] is None


# --- visibility (SD rule) ------------------------------------------------------------


async def test_only_public_products_and_variants_are_listed(
    auth_client: AsyncClient, catalog: Catalog
) -> None:
    category = await catalog.category()
    shown = await _priced(catalog, category, 100_000)
    # A deleted or inactive variant counts for nothing, not even the price.
    deleted_variant = await catalog.variant(shown, base_price=10)
    await catalog.set(ProductVariant, deleted_variant.id, deleted_at=utc_now())
    await catalog.variant(shown, base_price=20, is_active=False)
    await _priced(catalog, category, 1, status=ProductStatus.DRAFT)
    await _priced(catalog, category, 1, status=ProductStatus.ARCHIVED, published_at=utc_now())
    deleted = await _priced(catalog, category, 1)
    await catalog.set(Product, deleted.id, deleted_at=utc_now())
    no_variant = await catalog.product(category=category.id)
    await catalog.variant(no_variant, is_active=False)
    child = await catalog.category(parent=category.id)
    await _priced(catalog, child, 1)  # sub-category products stay in their own list

    response = await _list(auth_client, category)

    assert _ids(response) == [str(shown.id)]
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["price_range"] == {"min": 100_000, "max": 100_000}


async def test_hidden_or_unknown_category_is_404(
    auth_client: AsyncClient, catalog: Catalog
) -> None:
    inactive = await catalog.category(active=False)
    child_of_inactive = await catalog.category(parent=inactive.id)
    deleted = await catalog.category()
    await catalog.set(Category, deleted.id, deleted_at=utc_now())

    for slug in (inactive.slug, child_of_inactive.slug, deleted.slug, unique_slug(), "X!"):
        response = await auth_client.get(f"/api/v1/categories/{slug}/products")
        assert response.status_code == 404, slug
        assert response.json()["error"]["code"] == "NOT_FOUND"
        response = await auth_client.get(PRODUCTS, params={"category_slug": slug})
        assert response.status_code == (400 if slug == "X!" else 404), slug


async def test_all_products_listing_spans_categories(
    auth_client: AsyncClient, catalog: Catalog
) -> None:
    tag = uuid4().hex
    first = await catalog.category()
    hidden = await catalog.category(active=False)
    one = await catalog.product(category=first.id, attributes={"tag": tag})
    await catalog.variant(one)
    # Its page is public (ADR-020), so it is listed outside its hidden category.
    two = await catalog.product(category=hidden.id, attributes={"tag": tag})
    await catalog.variant(two)

    response = await auth_client.get(PRODUCTS, params={"attributes": f"tag:{tag}"})
    assert sorted(_ids(response)) == sorted([str(one.id), str(two.id)])
    assert response.headers["cache-control"] == "no-store"

    scoped = await auth_client.get(
        PRODUCTS, params={"attributes": f"tag:{tag}", "category_slug": first.slug}
    )
    # In a category, only its active filters may be used.
    assert scoped.status_code == 422
    await catalog.filters(first, ("tag", "checkbox"))
    scoped = await auth_client.get(
        PRODUCTS, params={"attributes": f"tag:{tag}", "category_slug": first.slug}
    )
    assert _ids(scoped) == [str(one.id)]


# --- validation ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "params",
    [
        {"unknown": "1"},
        {"sort": "cheapest"},
        {"page": "0"},
        {"page": "1001"},
        {"limit": "49"},
        {"min_price": "-1"},
        {"max_price": "x"},
        {"min_price": "10", "max_price": "9"},
        {"in_stock": "maybe"},
        {"colors": ["c"] * (MAX_FILTER_VALUES + 1)},
        {"colors": "x" * 201},
        {"colors": " "},
        {"attributes": "no-colon"},
        {"attributes": ":value"},
        {"attributes": "key:"},
        {"attributes": f"{'k' * 51}:v"},
    ],
)
async def test_invalid_query_is_400(
    auth_client: AsyncClient, catalog: Catalog, params: dict[str, Any]
) -> None:
    category = await catalog.category()
    await catalog.filters(category, ("color", "color"))

    for response in (
        await _list(auth_client, category, **params),
        await auth_client.get(PRODUCTS, params=params),
    ):
        assert response.status_code == 400, response.text
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_filter_not_in_category_is_422(auth_client: AsyncClient, catalog: Catalog) -> None:
    category = await catalog.category()
    await catalog.filters(category, ("color", "color"), ("price", "range"))
    await _priced(catalog, category, 100)

    for params in ({"sizes": "M"}, {"attributes": "brand:x"}, {"materials": "gold"}):
        response = await _list(auth_client, category, **params)
        assert response.status_code == 422, params
        error = response.json()["error"]
        assert error["code"] == "BUSINESS_RULE_VIOLATION"
        assert error["details"][0]["type"] == "filter_not_applicable"
    assert (await _list(auth_client, category, colors="red")).status_code == 200
    # Price, stock and discount filters are always available.
    assert (await _list(auth_client, category, min_price=1, in_stock="true")).status_code == 200


# --- filters -------------------------------------------------------------------------


async def test_price_filter_uses_the_current_final_price(
    auth_client: AsyncClient, catalog: Catalog
) -> None:
    category = await catalog.category()
    now = utc_now()
    on_sale = await catalog.product(category=category.id)
    await catalog.variant(on_sale, base_price=500, sale_price=100, sale_start_at=now - timedelta(1))
    expired = await catalog.product(category=category.id)
    await catalog.variant(
        expired,
        base_price=500,
        sale_price=100,
        sale_start_at=now - timedelta(days=2),
        sale_end_at=now - timedelta(days=1),
    )
    future = await catalog.product(category=category.id)
    await catalog.variant(future, base_price=500, sale_price=100, sale_start_at=now + timedelta(1))

    assert _ids(await _list(auth_client, category, max_price=100)) == [str(on_sale.id)]
    assert sorted(_ids(await _list(auth_client, category, min_price=101))) == sorted(
        [str(expired.id), str(future.id)]
    )
    assert _ids(await _list(auth_client, category, min_price=100, max_price=100)) == [
        str(on_sale.id)
    ]
    assert _ids(await _list(auth_client, category, has_discount="true")) == [str(on_sale.id)]
    # false means "no restriction", like leaving the filter out.
    assert len(_ids(await _list(auth_client, category, has_discount="false"))) == 3


async def test_in_stock_filter(auth_client: AsyncClient, catalog: Catalog) -> None:
    category = await catalog.category()
    stocked = await catalog.product(category=category.id)
    await catalog.variant(stocked, stock=(0, 0, 0))
    await catalog.variant(stocked, stock=(3, 2, 5))  # low stock still counts
    reserved = await catalog.product(category=category.id)
    await catalog.variant(reserved, stock=(2, 2, 0))
    no_item = await catalog.product(category=category.id)
    await catalog.variant(no_item)
    inactive = await catalog.product(category=category.id)
    await catalog.variant(inactive)
    await catalog.variant(inactive, stock=(9, 0, 0), is_active=False)

    assert _ids(await _list(auth_client, category, in_stock="true")) == [str(stocked.id)]
    assert len(_ids(await _list(auth_client, category))) == 4


async def test_option_and_attribute_filters(auth_client: AsyncClient, catalog: Catalog) -> None:
    category = await catalog.category()
    await catalog.filters(category, ("color", "color"), ("size", "select"), ("brand", "checkbox"))

    async def make(options: list[dict[str, str]], brand: str, **variant: Any) -> Product:
        product = await catalog.product(category=category.id, attributes={"brand": brand})
        for item in options:
            await catalog.variant(product, options=item, **variant)
        return product

    gold_m = await make([{"color": "gold", "size": "M"}], "acme")
    silver_s = await make([{"color": "silver", "size": "S"}], "acme")
    red = await make([{"color": "red"}], "other")
    # A colour only an inactive variant has does not match.
    hidden_gold = await catalog.product(category=category.id, attributes={"brand": "acme"})
    await catalog.variant(hidden_gold, options={"color": "silver"})
    await catalog.variant(hidden_gold, options={"color": "gold"}, is_active=False)

    gold = await _list(auth_client, category, colors="gold")
    assert _ids(gold) == [str(gold_m.id)]
    either = await _list(auth_client, category, colors=["gold", "red"])
    assert sorted(_ids(either)) == sorted([str(gold_m.id), str(red.id)])
    both = await _list(auth_client, category, colors=["gold", "silver"], sizes="S")
    assert _ids(both) == [str(silver_s.id)]
    acme = await _list(auth_client, category, attributes="brand:acme", colors="silver")
    assert sorted(_ids(acme)) == sorted([str(silver_s.id), str(hidden_gold.id)])
    assert _ids(await _list(auth_client, category, brands="other")) == [str(red.id)]


async def test_price_range_filter_bounds(auth_client: AsyncClient, catalog: Catalog) -> None:
    category = await catalog.category()
    await catalog.filters(category, ("price", "range"))
    response = await auth_client.get(f"/api/v1/categories/{category.slug}/filters")
    assert response.json()["items"] == []  # no products yet

    await _priced(catalog, category, 300)
    await _priced(catalog, category, 1_200)
    response = await auth_client.get(f"/api/v1/categories/{category.slug}/filters")

    assert response.json()["items"] == [
        {"key": "price", "label": "Price", "type": "range", "values": [], "min": 300, "max": 1_200}
    ]


# --- sort and pagination -------------------------------------------------------------


async def test_sorts(auth_client: AsyncClient, catalog: Catalog) -> None:
    category = await catalog.category()
    now = utc_now()
    old = await _priced(catalog, category, 300, published_at=now - timedelta(days=3))
    mid = await catalog.product(category=category.id, published_at=now - timedelta(days=2))
    await catalog.variant(mid, base_price=1_000, sale_price=100, sale_start_at=now - timedelta(1))
    new = await _priced(catalog, category, 200, published_at=now - timedelta(days=1))

    async def order(sort: str | None = None) -> list[UUID]:
        params = {} if sort is None else {"sort": sort}
        return [UUID(item) for item in _ids(await _list(auth_client, category, **params))]

    assert await order() == [new.id, mid.id, old.id]  # newest is the default
    assert await order("price_asc") == [mid.id, new.id, old.id]
    assert await order("price_desc") == [old.id, new.id, mid.id]
    assert await order("discount_desc") == [mid.id, new.id, old.id]

    # Card prices agree with the SQL sort key.
    cards = (await _list(auth_client, category, sort="price_asc")).json()["items"]
    finals = [card["price"]["final_price"] for card in cards]
    assert finals == sorted(finals) == [100, 200, 300]


async def test_pages_neither_repeat_nor_skip_ties(
    auth_client: AsyncClient, catalog: Catalog
) -> None:
    category = await catalog.category()
    published_at = utc_now() - timedelta(hours=1)
    # Every product ties on every sort key, so only the id tie-break orders them.
    created = {
        str((await _priced(catalog, category, 500, published_at=published_at)).id) for _ in range(7)
    }

    for sort in ("newest", "price_asc", "price_desc", "discount_desc", "best_selling"):
        seen: list[str] = []
        for page in (1, 2, 3):
            response = await _list(auth_client, category, sort=sort, limit=3, page=page)
            body = response.json()
            assert (body["total"], body["pages"]) == (7, 3)
            seen += _ids(response)
        assert len(seen) == 7 and set(seen) == created, sort
        again = _ids(await _list(auth_client, category, sort=sort, limit=7))
        assert again == seen, sort
    beyond = await _list(auth_client, category, page=4, limit=3)
    assert _ids(beyond) == [] and beyond.json()["total"] == 7


async def test_best_selling_counts_units_of_paid_orders_only(
    auth_client: AsyncClient, catalog: Catalog, make_order: MakeOrder, db_engine: AsyncEngine
) -> None:
    category = await catalog.category()
    products = [await _priced(catalog, category, 1_000) for _ in range(4)]
    variants = {}
    async with AsyncSession(db_engine) as session:
        for product in products:
            variants[product.id] = (
                await session.scalars(
                    select(ProductVariant).where(ProductVariant.product_id == product.id)
                )
            ).one()

    async def sell(product: Product, quantity: int, payment_status: str) -> None:
        extra = {"status": "cancelled", "cancel_reason": "expired"}
        order_id = await make_order(
            payment_status=payment_status, **(extra if payment_status == "refund_required" else {})
        )
        variant = variants[product.id]
        async with AsyncSession(db_engine) as session, session.begin():
            session.add(
                OrderItem(
                    order_id=order_id,
                    position=0,
                    product_id=product.id,
                    variant_id=variant.id,
                    product_title=product.title,
                    sku=variant.sku,
                    quantity=quantity,
                    unit_price=1_000,
                    unit_final_price=1_000,
                    subtotal=1_000 * quantity,
                    product_discount=0,
                    code_discount=0,
                    discount_amount=0,
                    tax_amount=0,
                    final_line_total=1_000 * quantity,
                )
            )

    first, second, unpaid_only, none = products
    await sell(first, 2, "paid")
    await sell(first, 3, "paid")
    await sell(second, 4, "paid")
    await sell(second, 9, "refund_required")
    await sell(unpaid_only, 50, "unpaid")
    await sell(unpaid_only, 50, "failed")

    ordered = _ids(await _list(auth_client, category, sort="best_selling"))

    # 5 > 4 > 0 = 0, and the two unsold products tie by id.
    assert ordered[:2] == [str(first.id), str(second.id)]
    assert ordered[2:] == sorted([str(unpaid_only.id), str(none.id)])


# --- queries -------------------------------------------------------------------------


async def test_query_count_does_not_grow_with_products(
    auth_client: AsyncClient, catalog: Catalog
) -> None:
    small = await catalog.category()
    product = await catalog.product(category=small.id)
    await catalog.variant(product, options={"color": "gold"}, stock=(1, 0, 0))
    await catalog.image(product, is_main=True)
    large = await catalog.category()
    for _ in range(5):
        product = await catalog.product(category=large.id)
        for index in range(3):
            await catalog.variant(product, options={"color": f"c{index}"}, stock=(1, 0, 0))
        await catalog.image(product, is_main=True)
    await _list(auth_client, small)  # warm-up (connection setup)

    with count_queries(auth_client) as small_queries:
        assert len(_ids(await _list(auth_client, small))) == 1
    with count_queries(auth_client) as large_queries:
        assert len(_ids(await _list(auth_client, large))) == 5

    assert len(large_queries) == len(small_queries)
