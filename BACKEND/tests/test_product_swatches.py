"""Colour swatches and the "new" badge on product summaries (CAT-18, D42)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from conftest import Account, Catalog, count_queries
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from test_admin_products import (
    VARIANTS_URL,
    Created,
    _audits,
    _create_variant,
    _product,
    _variant,
    admin,
    created,
)

from app.core.time import utc_now
from app.db.models import Category, Product, VariantOption
from app.modules.catalog.product_service import MAX_CARD_SWATCHES

pytestmark = pytest.mark.integration

__all__ = ["admin", "created"]  # fixtures shared with the admin product tests

PRODUCTS = "/api/v1/products"


async def _card(client: AsyncClient, category: Category) -> dict[str, Any]:
    response = await client.get(f"/api/v1/categories/{category.slug}/products")
    assert response.status_code == 200, response.text
    [card] = response.json()["items"]
    return card  # type: ignore[no-any-return]


async def _age(engine: AsyncEngine, product: Product, days: float) -> None:
    async with AsyncSession(engine) as session, session.begin():
        await session.execute(
            update(Product)
            .where(Product.id == product.id)
            .values(created_at=utc_now() - timedelta(days=days))
        )


async def test_card_swatches_follow_variant_order_and_are_capped(
    auth_client: AsyncClient, catalog: Catalog
) -> None:
    category = await catalog.category()
    product = await catalog.product(category=category.id)
    colors = ["Gold", "Silver", "Rose", "Black", "White", "Blue", "Green"]
    for order, color in enumerate(colors):
        await catalog.variant(
            product,
            options={"color": color, "size": "M"},
            color_hex=f"#00000{order}",
            display_order=order + 1,
            stock=(1, 0, 0),
        )
    # A repeated colour is one swatch; the first variant's hex wins.
    await catalog.variant(
        product, options={"color": "Gold", "size": "L"}, color_hex="#FFFFFF", display_order=9
    )
    # Not public (inactive): its colour is not shown.
    await catalog.variant(product, options={"color": "Hidden"}, is_active=False, display_order=0)

    card = await _card(auth_client, category)

    assert len(card["color_swatches"]) == MAX_CARD_SWATCHES == 5
    assert card["color_swatches"] == [
        {"value": color, "hex": f"#00000{order}"} for order, color in enumerate(colors[:5])
    ]


async def test_a_colour_without_hex_and_a_product_without_colours(
    auth_client: AsyncClient, catalog: Catalog
) -> None:
    category = await catalog.category()
    product = await catalog.product(category=category.id)
    await catalog.variant(product, options={"color": "Amber"})
    plain_category = await catalog.category()
    plain = await catalog.product(category=plain_category.id)
    await catalog.variant(plain, options={"size": "S"})

    assert (await _card(auth_client, category))["color_swatches"] == [
        {"value": "Amber", "hex": None}
    ]
    assert (await _card(auth_client, plain_category))["color_swatches"] == []


@pytest.mark.parametrize(("days", "is_new"), [(0, True), (29.9, True), (30.1, False)])
async def test_is_new_uses_the_creation_date(
    auth_client: AsyncClient,
    catalog: Catalog,
    db_engine: AsyncEngine,
    days: float,
    is_new: bool,
) -> None:
    category = await catalog.category()
    product = await catalog.product(category=category.id)
    await catalog.variant(product)
    await _age(db_engine, product, days)

    assert (await _card(auth_client, category))["is_new"] is is_new
    detail = (await auth_client.get(f"{PRODUCTS}/{product.slug}")).json()
    assert detail["is_new"] is is_new


async def test_detail_lists_every_colour_with_its_hex(
    auth_client: AsyncClient, catalog: Catalog
) -> None:
    product = await catalog.product()
    for order, color in enumerate(["C1", "C2", "C3", "C4", "C5", "C6"]):
        await catalog.variant(
            product, options={"color": color}, color_hex="#ABCDEF", display_order=order
        )

    body = (await auth_client.get(f"{PRODUCTS}/{product.slug}")).json()

    assert len(body["color_swatches"]) == 6  # the detail is not capped
    assert {variant["color_hex"] for variant in body["variants"]} == {"#ABCDEF"}


async def test_listing_query_count_does_not_grow_with_colours(
    auth_client: AsyncClient, catalog: Catalog
) -> None:
    category = await catalog.category()

    async def listed() -> int:
        with count_queries(auth_client) as queries:
            response = await auth_client.get(f"/api/v1/categories/{category.slug}/products")
        assert response.status_code == 200
        return len(queries)

    product = await catalog.product(category=category.id)
    await catalog.variant(product, options={"color": "A"}, color_hex="#000000")
    few = await listed()
    for _ in range(3):
        more = await catalog.product(category=category.id)
        for color in ("B", "C"):
            await catalog.variant(more, options={"color": color}, color_hex="#111111")

    assert await listed() == few


# --- admin ---------------------------------------------------------------------------


async def test_admin_sets_and_changes_the_hex(
    auth_client: AsyncClient, admin: Account, created: Created, db_engine: AsyncEngine
) -> None:
    product_id = await _product(auth_client, admin, created)
    response = await _create_variant(
        auth_client, admin, product_id, options={"color": "Gold", "color_hex": " #d4af37 "}
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["color_hex"] == "#D4AF37"
    assert body["options"] == {"color": "Gold"}
    variant_id = UUID(body["id"])

    # Only the swatch changes: still an update, audited with before and after.
    changed = await auth_client.patch(
        f"{VARIANTS_URL}/{variant_id}",
        json={"options": {"color": "Gold", "color_hex": "#C0C0C0"}},
        headers=admin.headers,
    )
    same = await auth_client.patch(
        f"{VARIANTS_URL}/{variant_id}",
        json={"options": {"color": "Gold", "color_hex": "#c0c0c0"}},
        headers=admin.headers,
    )

    assert changed.status_code == 200, changed.text
    assert changed.json()["color_hex"] == "#C0C0C0"
    assert same.status_code == 200
    audits = await _audits(db_engine, variant_id)
    assert [audit.action for audit in audits] == [
        "product_variant.created",
        "product_variant.updated",
    ]
    assert audits[1].metadata_["diff"]["color_hex"] == {
        "before": "#D4AF37",
        "after": "#C0C0C0",
        "changed": True,
    }


@pytest.mark.parametrize(
    "options",
    [
        {"color": "Gold", "color_hex": "#GGGGGG"},
        {"color": "Gold", "color_hex": "D4AF37"},
        {"color": "Gold", "color_hex": "#D4AF3"},
        {"size": "M", "color_hex": "#D4AF37"},
    ],
)
async def test_invalid_hex_is_400(
    auth_client: AsyncClient, admin: Account, created: Created, options: dict[str, str]
) -> None:
    product_id = await _product(auth_client, admin, created)

    response = await _create_variant(auth_client, admin, product_id, options=options)

    assert response.status_code == 400, response.text


async def test_the_database_keeps_hex_on_colours_only(
    auth_client: AsyncClient, admin: Account, created: Created, db_engine: AsyncEngine
) -> None:
    product_id = await _product(auth_client, admin, created)
    variant_id = await _variant(auth_client, admin, product_id, options={"size": "M"})

    for row in (
        VariantOption(variant_id=variant_id, option_key="model", value="X", hex="#000000"),
        VariantOption(variant_id=variant_id, option_key="color", value="Y", hex="#abcdef"),
    ):
        with pytest.raises(IntegrityError, match="hex_only_on_color"):
            async with AsyncSession(db_engine) as session, session.begin():
                session.add(row)
