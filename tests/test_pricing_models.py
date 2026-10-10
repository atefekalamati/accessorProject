from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest
from alembic.config import Config
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from alembic import command
from app.core.time import utc_now
from app.db.models import Category, PricingSetting, Product, ProductStatus, ProductVariant
from app.shared.money import MAX_PRICE_TOMAN

pytestmark = pytest.mark.integration

PRE_PRICING_REVISION = "20261010_0010"
PRICING_SETTINGS_ID = uuid5(NAMESPACE_URL, "project-ak:pricing_settings")
# One instant for both window ends: two utc_now() calls differ on fine-grained clocks.
NOW = utc_now()


def _slug(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


def _sku() -> str:
    return f"SKU-{uuid4().hex[:10].upper()}"


async def _product(session: AsyncSession) -> Product:
    category = Category(title="Category", slug=_slug("cat"))
    session.add(category)
    await session.flush()
    product = Product(category_id=category.id, title="Product", slug=_slug("prd"))
    session.add(product)
    await session.flush()
    return product


async def _variant(session: AsyncSession, **overrides: Any) -> ProductVariant:
    product = await _product(session)
    variant = ProductVariant(product_id=product.id, sku=_sku(), **overrides)
    session.add(variant)
    await session.flush()
    await session.refresh(variant)
    return variant


# --- variant prices ------------------------------------------------------------------


async def test_variant_price_defaults(db_session: AsyncSession) -> None:
    variant = await _variant(db_session)

    assert (variant.base_price, variant.sale_price) == (None, None)
    assert (variant.sale_start_at, variant.sale_end_at) == (None, None)
    assert variant.tax_enabled is False
    assert variant.price_version == 0
    assert variant.is_active is False


@pytest.mark.parametrize(
    "fields",
    [
        {"base_price": 1},
        {"base_price": MAX_PRICE_TOMAN},
        {"base_price": 150_000, "sale_price": 120_000},
        {"base_price": 150_000, "sale_price": 150_000},
        {"base_price": 150_000, "sale_price": 120_000, "sale_start_at": utc_now()},
        {"base_price": 150_000, "sale_price": 120_000, "sale_end_at": utc_now()},
        {"base_price": 150_000, "is_active": True},
        {"is_active": False},
    ],
)
async def test_valid_variant_prices(db_session: AsyncSession, fields: dict[str, Any]) -> None:
    variant = await _variant(db_session, **fields)

    assert variant.base_price == fields.get("base_price")


@pytest.mark.parametrize(
    "fields",
    [
        {"base_price": 0},
        {"base_price": -1},
        {"base_price": MAX_PRICE_TOMAN + 1},
        {"base_price": 100, "sale_price": 101},
        {"base_price": 100, "sale_price": 0},
        {"sale_price": 100},
        {"base_price": 100, "sale_start_at": NOW},
        {"base_price": 100, "sale_price": 90, "sale_start_at": NOW, "sale_end_at": NOW},
        {
            "base_price": 100,
            "sale_price": 90,
            "sale_start_at": NOW,
            "sale_end_at": NOW - timedelta(days=1),
        },
        {"base_price": 100, "price_version": -1},
        {"is_active": True},
    ],
    ids=[
        "base-zero",
        "base-negative",
        "base-over-cap",
        "sale-over-base",
        "sale-zero",
        "sale-without-base",
        "window-without-sale",
        "window-empty",
        "window-reversed",
        "negative-version",
        "active-without-price",
    ],
)
async def test_invalid_variant_prices(db_session: AsyncSession, fields: dict[str, Any]) -> None:
    with pytest.raises(IntegrityError):
        await _variant(db_session, **fields)


# --- pricing settings ----------------------------------------------------------------


async def test_pricing_settings_row_has_v1_defaults(db_session: AsyncSession) -> None:
    rows = (await db_session.scalars(select(PricingSetting))).all()

    assert len(rows) == 1
    setting = rows[0]
    assert setting.id == PRICING_SETTINGS_ID
    assert (setting.currency, setting.tax_enabled, setting.default_tax_rate_bps) == (
        "TOMAN",
        False,
        0,
    )
    assert (setting.rounding_mode, setting.rounding_step, setting.version) == ("nearest", 1, 1)


async def test_second_pricing_settings_row_is_rejected(db_session: AsyncSession) -> None:
    db_session.add(PricingSetting())

    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.parametrize(
    "values",
    [
        {"singleton": False},
        {"currency": "IRR"},
        {"default_tax_rate_bps": -1},
        {"default_tax_rate_bps": 10_001},
        {"rounding_mode": "banker"},
        {"rounding_step": 0},
        {"rounding_step": 1_000_001},
        {"version": 0},
    ],
)
async def test_pricing_settings_constraints(
    db_session: AsyncSession, values: dict[str, Any]
) -> None:
    with pytest.raises(IntegrityError):
        await db_session.execute(
            update(PricingSetting).where(PricingSetting.id == PRICING_SETTINGS_ID).values(**values)
        )


# --- migration -----------------------------------------------------------------------


async def _alembic(database_url: str, action: str, revision: str) -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    # env.py calls asyncio.run, which cannot run inside the test's event loop.
    await asyncio.to_thread(getattr(command, action), config, revision)


async def _insert_variant(engine: AsyncEngine, *, published: bool) -> tuple[str, str]:
    """Insert a category, product and active variant on the pre-pricing schema (raw SQL:
    the models already have the price columns)."""
    category_slug, product_slug, sku = _slug("cat"), _slug("prd"), _sku()
    async with AsyncSession(engine) as session, session.begin():
        await session.execute(
            text("INSERT INTO categories (title, slug) VALUES ('Category', :slug)"),
            {"slug": category_slug},
        )
        await session.execute(
            text(
                "INSERT INTO products (category_id, title, slug, status, published_at) "
                "SELECT id, 'Product', :slug, :status, :published_at "
                "FROM categories WHERE slug = :category_slug"
            ),
            {
                "slug": product_slug,
                "status": ProductStatus.PUBLISHED if published else ProductStatus.DRAFT,
                "published_at": utc_now() if published else None,
                "category_slug": category_slug,
            },
        )
        await session.execute(
            text(
                "INSERT INTO product_variants (product_id, sku, is_active) "
                "SELECT id, :sku, true FROM products WHERE slug = :product_slug"
            ),
            {"sku": sku, "product_slug": product_slug},
        )
    return category_slug, sku


async def _remove(engine: AsyncEngine, category_slug: str) -> None:
    async with AsyncSession(engine) as session, session.begin():
        products = (
            "SELECT p.id FROM products p JOIN categories c ON c.id = p.category_id "
            "WHERE c.slug = :slug"
        )
        await session.execute(
            text(f"DELETE FROM product_variants WHERE product_id IN ({products})"),
            {"slug": category_slug},
        )
        await session.execute(
            text(f"DELETE FROM products WHERE id IN ({products})"), {"slug": category_slug}
        )
        await session.execute(delete(Category).where(Category.slug == category_slug))


async def test_migration_deactivates_price_less_variants_and_is_repeatable(
    db_engine: AsyncEngine, migrated_database: str
) -> None:
    category_slug = ""
    try:
        await _alembic(migrated_database, "downgrade", PRE_PRICING_REVISION)
        category_slug, sku = await _insert_variant(db_engine, published=False)

        await _alembic(migrated_database, "upgrade", "head")
        async with AsyncSession(db_engine) as session:
            active = await session.scalar(
                select(ProductVariant.is_active).where(ProductVariant.sku == sku)
            )
            settings_rows = await session.scalar(select(func.count()).select_from(PricingSetting))
        assert active is False
        assert settings_rows == 1

        # A second round trip re-creates the singleton with the same id, not a duplicate.
        await _alembic(migrated_database, "downgrade", PRE_PRICING_REVISION)
        await _alembic(migrated_database, "upgrade", "head")
        async with AsyncSession(db_engine) as session:
            ids = (await session.scalars(select(PricingSetting.id))).all()
        assert ids == [PRICING_SETTINGS_ID]
    finally:
        await _alembic(migrated_database, "upgrade", "head")
        if category_slug:
            await _remove(db_engine, category_slug)


async def test_migration_refuses_price_less_active_variant_of_published_product(
    db_engine: AsyncEngine, migrated_database: str
) -> None:
    category_slug = ""
    try:
        await _alembic(migrated_database, "downgrade", PRE_PRICING_REVISION)
        category_slug, _sku_value = await _insert_variant(db_engine, published=True)

        with pytest.raises(RuntimeError, match="published products have no price"):
            await _alembic(migrated_database, "upgrade", "head")
    finally:
        if category_slug:
            await _remove(db_engine, category_slug)
        await _alembic(migrated_database, "upgrade", "head")
