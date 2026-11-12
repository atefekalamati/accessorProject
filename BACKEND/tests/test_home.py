"""GET /home: sections, carousels, SD rule, targets, defaults, failure isolation (CNT-01)."""

from __future__ import annotations

import itertools
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from conftest import INTERNAL_FIELDS, Catalog, nested_keys
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.time import utc_now
from app.db.models import (
    Category,
    HomeSection,
    HomeSectionItem,
    Product,
    ProductStatus,
    StaticPage,
)
from app.modules.content.home import HomeService

pytestmark = pytest.mark.integration

URL = "/api/v1/home"
_ORDERS = itertools.count(uuid4().int % 100_000 * 10)


@pytest_asyncio.fixture(autouse=True)
async def _cleanup(db_engine: AsyncEngine, catalog: Catalog) -> AsyncIterator[None]:
    """Torn down before ``catalog``: items hold its products and categories (RESTRICT)."""
    started = utc_now()
    yield
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(HomeSection))
        await session.execute(delete(StaticPage).where(StaticPage.created_at >= started))


async def _section(engine: AsyncEngine, *items: dict[str, Any], **fields: Any) -> HomeSection:
    """A section inserted directly; text items by default (``benefits``)."""
    values: dict[str, Any] = {
        "type": "benefits",
        "title": "Why us",
        "display_order": next(_ORDERS),
    } | fields
    if not items and values["type"] in ("benefits", "editorial"):
        items = ({"title_override": "Fast", "body": "Two days"},)
    section = HomeSection(**values)
    async with AsyncSession(engine, expire_on_commit=False) as session, session.begin():
        session.add(section)
        await session.flush()
        session.add_all(
            HomeSectionItem(section_id=section.id, display_order=index, **item)
            for index, item in enumerate(items)
        )
    return section


async def _home(client: AsyncClient) -> dict[str, Any]:
    response = await client.get(URL)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body: dict[str, Any] = response.json()
    return body


def _section_ids(body: dict[str, Any]) -> list[str | None]:
    return [section["id"] for section in body["sections"]]


def _product_ids(section: dict[str, Any]) -> list[str]:
    return [item["product"]["id"] for item in section["items"]]


async def _published(catalog: Catalog, **fields: Any) -> Product:
    product = await catalog.product(**fields)
    await catalog.variant(
        product, options={"color": "Silver"}, color_hex="#C0C0C0", stock=(5, 0, 0)
    )
    return product


async def test_only_live_active_sections_in_their_window_in_order(
    auth_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    now = utc_now()
    first = await _section(db_engine)
    second = await _section(db_engine)
    await _section(db_engine, is_active=False)
    await _section(db_engine, starts_at=now + timedelta(hours=1))
    await _section(db_engine, ends_at=now - timedelta(seconds=1))
    await _section(db_engine, deleted_at=now)
    shown_window = await _section(
        db_engine, starts_at=now - timedelta(hours=1), ends_at=now + timedelta(hours=1)
    )

    body = await _home(auth_client)

    assert _section_ids(body) == [str(first.id), str(second.id), str(shown_window.id)]
    assert body["sections"][0]["items"] == [
        {
            "title": "Fast",
            "subtitle": None,
            "body": "Two days",
            "icon_key": None,
            "image_url": None,
            "mobile_image_url": None,
            "target": None,
            "product": None,
            "category": None,
        }
    ]


async def test_a_section_without_public_items_is_not_shown(
    auth_client: AsyncClient, db_engine: AsyncEngine, catalog: Catalog
) -> None:
    hidden = await catalog.category(active=False)
    draft = await catalog.product(status=ProductStatus.DRAFT)
    kept = await _section(db_engine)
    await _section(db_engine, {"category_id": hidden.id}, type="category_grid")
    await _section(
        db_engine, {"product_id": draft.id}, type="product_carousel", product_source="manual"
    )
    await _section(db_engine, type="hero")

    assert _section_ids(await _home(auth_client)) == [str(kept.id)]


async def test_manual_carousel_keeps_its_order_and_drops_hidden_products(
    auth_client: AsyncClient, db_engine: AsyncEngine, catalog: Catalog
) -> None:
    first = await _published(catalog)
    draft = await _published(catalog, status=ProductStatus.DRAFT)
    second = await _published(catalog)
    deleted = await _published(catalog)
    await catalog.set(Product, deleted.id, deleted_at=utc_now())
    section = await _section(
        db_engine,
        {"product_id": second.id, "title_override": "Pick"},
        {"product_id": draft.id},
        {"product_id": first.id},
        {"product_id": deleted.id},
        type="product_carousel",
        product_source="manual",
    )

    [shown] = (await _home(auth_client))["sections"]

    assert shown["id"] == str(section.id)
    assert _product_ids(shown) == [str(second.id), str(first.id)]
    assert [item["title"] for item in shown["items"]] == ["Pick", None]
    card = shown["items"][0]["product"]
    assert card["color_swatches"] == [{"value": "Silver", "hex": "#C0C0C0"}]
    assert card["is_new"] is True
    assert card["availability"] == "in_stock"


async def test_the_source_fills_after_manual_items_without_duplicates(
    auth_client: AsyncClient, db_engine: AsyncEngine, catalog: Catalog
) -> None:
    category = await catalog.category()
    now = utc_now()
    oldest, middle, newest = [
        await _published(catalog, category=category.id, published_at=now - timedelta(days=days))
        for days in (3, 2, 1)
    ]
    await _published(catalog)  # another category: never in this section
    await _section(
        db_engine,
        {"product_id": middle.id},
        type="product_carousel",
        product_source="category",
        source_category_id=category.id,
        product_limit=3,
    )

    [shown] = (await _home(auth_client))["sections"]

    assert _product_ids(shown) == [str(middle.id), str(newest.id), str(oldest.id)]


async def test_the_product_limit_caps_the_carousel(
    auth_client: AsyncClient, db_engine: AsyncEngine, catalog: Catalog
) -> None:
    category = await catalog.category()
    for _ in range(3):
        await _published(catalog, category=category.id)
    await _section(
        db_engine,
        type="product_carousel",
        product_source="category",
        source_category_id=category.id,
        product_limit=2,
    )

    [shown] = (await _home(auth_client))["sections"]

    assert len(shown["items"]) == 2


async def test_a_hidden_source_category_shows_nothing_from_it(
    auth_client: AsyncClient, db_engine: AsyncEngine, catalog: Catalog
) -> None:
    category = await catalog.category()
    await _published(catalog, category=category.id)
    await catalog.set(Category, category.id, is_active=False)
    kept = await _section(db_engine)
    await _section(
        db_engine,
        type="product_carousel",
        product_source="category",
        source_category_id=category.id,
    )

    assert _section_ids(await _home(auth_client)) == [str(kept.id)]


async def test_discount_source_lists_only_discounted_products(
    auth_client: AsyncClient, db_engine: AsyncEngine, catalog: Catalog
) -> None:
    category = await catalog.category()
    plain = await catalog.product(category=category.id)
    await catalog.variant(plain, stock=(5, 0, 0))
    on_sale = await catalog.product(category=category.id)
    await catalog.variant(on_sale, stock=(5, 0, 0), sale_price=80_000)
    await _section(db_engine, type="product_carousel", product_source="discount")

    [shown] = (await _home(auth_client))["sections"]

    ids = _product_ids(shown)
    assert str(on_sale.id) in ids
    assert str(plain.id) not in ids


async def test_category_grid_shows_only_visible_categories(
    auth_client: AsyncClient, db_engine: AsyncEngine, catalog: Catalog, make_media: Any
) -> None:
    visible = await catalog.category()
    inactive = await catalog.category(active=False)
    under_inactive = await catalog.category(parent=inactive.id)
    image = await make_media()
    await _section(
        db_engine,
        {"category_id": inactive.id},
        {"category_id": visible.id, "title_override": "Rings!", "image_media_id": image.id},
        {"category_id": under_inactive.id},
        type="category_grid",
    )

    [shown] = (await _home(auth_client))["sections"]

    [item] = shown["items"]
    assert item["title"] == "Rings!"
    assert item["image_url"].endswith(image.storage_key)
    assert item["category"]["slug"] == visible.slug


async def test_a_section_link_must_still_be_public(
    auth_client: AsyncClient, db_engine: AsyncEngine, catalog: Catalog
) -> None:
    page = StaticPage(slug=f"pg-{uuid4().hex[:8]}", title="About", body="Hi", status="draft")
    async with AsyncSession(db_engine, expire_on_commit=False) as session, session.begin():
        session.add(page)
    product = await _published(catalog)
    hidden = await catalog.category(active=False)
    to_page = await _section(db_engine, target_type="page", target_id=page.id)
    to_product = await _section(db_engine, target_type="product", target_id=product.id)
    await _section(db_engine, target_type="category", target_id=hidden.id)
    await _section(db_engine, target_type="product", target_id=uuid4())

    body = await _home(auth_client)
    assert _section_ids(body) == [str(to_product.id)]
    assert body["sections"][0]["target"] == {"type": "product", "slug": product.slug}

    await catalog.set(StaticPage, page.id, status="published", published_at=utc_now())
    body = await _home(auth_client)
    assert _section_ids(body) == [str(to_page.id), str(to_product.id)]
    assert body["sections"][0]["target"] == {"type": "page", "slug": page.slug}


async def test_one_failing_section_does_not_break_the_page(
    auth_client: AsyncClient,
    db_engine: AsyncEngine,
    catalog: Catalog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product = await _published(catalog)
    await _section(
        db_engine, {"product_id": product.id}, type="product_carousel", product_source="manual"
    )
    kept = await _section(db_engine)

    async def broken(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("boom")

    monkeypatch.setattr(HomeService, "_carousel", broken)

    assert _section_ids(await _home(auth_client)) == [str(kept.id)]


async def test_default_layout_when_no_section_is_active(
    auth_client: AsyncClient, db_engine: AsyncEngine, catalog: Catalog
) -> None:
    category = await catalog.category()
    product = await _published(catalog, category=category.id)
    await _section(db_engine, is_active=False)

    body = await _home(auth_client)

    assert _section_ids(body) == [None, None]
    grid, newest = body["sections"]
    assert (grid["type"], newest["type"]) == ("category_grid", "product_carousel")
    assert category.slug in {item["category"]["slug"] for item in grid["items"]}
    assert str(product.id) in _product_ids(newest)


async def test_guests_see_no_internal_fields(
    auth_client: AsyncClient, db_engine: AsyncEngine, catalog: Catalog
) -> None:
    product = await _published(catalog)
    await _section(
        db_engine, {"product_id": product.id}, type="product_carousel", product_source="newest"
    )
    await _section(db_engine)

    body = await _home(auth_client)

    assert len(body["sections"]) == 2
    assert not nested_keys(body) & (INTERNAL_FIELDS | {"display_order", "target_id"})
