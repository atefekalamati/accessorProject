from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.time import utc_now
from app.db.models import (
    Category,
    Product,
    ProductAttribute,
    ProductStatus,
    ProductVariant,
    User,
    VariantOption,
    VariantOptionKey,
)

pytestmark = pytest.mark.integration


def _slug(prefix: str = "cat") -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


def _category(**overrides: object) -> Category:
    values: dict[str, object] = {"title": "Necklaces", "slug": _slug()}
    return Category(**{**values, **overrides})


async def _columns(db_engine: AsyncEngine, table: str) -> set[str]:
    async with db_engine.connect() as connection:
        return await connection.run_sync(
            lambda sync_connection: {
                column["name"] for column in inspect(sync_connection).get_columns(table)
            }
        )


async def test_category_defaults(db_session: AsyncSession) -> None:
    category = _category()
    db_session.add(category)
    await db_session.flush()
    await db_session.refresh(category)

    assert category.is_active is True
    assert category.display_order == 0
    assert category.parent_id is None
    assert category.deleted_at is None


async def test_category_tree_parent_and_children(db_session: AsyncSession) -> None:
    parent = _category(title="Jewelry")
    db_session.add(parent)
    await db_session.flush()
    children = [_category(parent_id=parent.id, display_order=order) for order in (2, 1)]
    db_session.add_all(children)
    await db_session.flush()

    ordered = (
        await db_session.scalars(
            select(Category.display_order)
            .where(Category.parent_id == parent.id)
            .order_by(Category.display_order)
        )
    ).all()
    assert ordered == [1, 2]


async def test_category_parent_must_exist(db_session: AsyncSession) -> None:
    db_session.add(_category(parent_id=uuid4()))

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_category_cannot_be_its_own_parent(db_session: AsyncSession) -> None:
    category = _category()
    db_session.add(category)
    await db_session.flush()

    category.parent_id = category.id
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_category_with_children_cannot_be_hard_deleted(db_session: AsyncSession) -> None:
    parent = _category()
    db_session.add(parent)
    await db_session.flush()
    db_session.add(_category(parent_id=parent.id))
    await db_session.flush()

    await db_session.delete(parent)
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_category_slug_unique_among_non_deleted(db_session: AsyncSession) -> None:
    slug = _slug()
    db_session.add(_category(slug=slug))
    await db_session.flush()

    db_session.add(_category(slug=slug))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_soft_deleted_category_frees_its_slug(db_session: AsyncSession) -> None:
    slug = _slug()
    old = _category(slug=slug)
    db_session.add(old)
    await db_session.flush()
    old.soft_delete()
    await db_session.flush()

    new = _category(slug=slug)
    db_session.add(new)
    await db_session.flush()

    assert new.id != old.id


@pytest.mark.parametrize(
    "overrides",
    [
        {"title": "   "},
        {"slug": "ab"},
        {"slug": "Necklaces"},
        {"slug": "gold necklace"},
        {"slug": "a" * 121},
        {"display_order": -1},
    ],
    ids=["blank-title", "short-slug", "uppercase-slug", "space-in-slug", "long-slug", "neg-order"],
)
async def test_category_constraints(db_session: AsyncSession, overrides: dict[str, object]) -> None:
    db_session.add(_category(**overrides))

    # CHECK violations raise IntegrityError; the String(120) overflow raises DataError.
    with pytest.raises(DBAPIError):
        await db_session.flush()


async def test_categories_table_columns(db_engine: AsyncEngine) -> None:
    assert await _columns(db_engine, "categories") == {
        "id",
        "parent_id",
        "title",
        "slug",
        "description",
        "icon_key",
        "image_url",
        "display_order",
        "is_active",
        "seo_title",
        "seo_description",
        "created_at",
        "updated_at",
        "deleted_at",
    }


async def _saved_category(db_session: AsyncSession) -> Category:
    category = _category()
    db_session.add(category)
    await db_session.flush()
    return category


def _product(category: Category, **overrides: object) -> Product:
    values: dict[str, object] = {
        "category_id": category.id,
        "title": "Gold necklace",
        "slug": _slug("product"),
    }
    return Product(**{**values, **overrides})


async def test_product_defaults_to_draft(db_session: AsyncSession) -> None:
    product = _product(await _saved_category(db_session))
    db_session.add(product)
    await db_session.flush()
    await db_session.refresh(product)

    assert product.status == ProductStatus.DRAFT
    assert product.published_at is None
    assert product.is_featured is False
    assert (product.created_by, product.updated_by, product.deleted_at) == (None, None, None)


async def test_product_requires_existing_category(db_session: AsyncSession) -> None:
    db_session.add(Product(category_id=uuid4(), title="Ring", slug=_slug("product")))

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_category_with_products_cannot_be_hard_deleted(db_session: AsyncSession) -> None:
    category = await _saved_category(db_session)
    db_session.add(_product(category))
    await db_session.flush()

    await db_session.delete(category)
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.parametrize("status", list(ProductStatus))
async def test_product_accepts_every_status(
    db_session: AsyncSession, status: ProductStatus
) -> None:
    published_at = None if status == ProductStatus.DRAFT else utc_now()
    product = _product(await _saved_category(db_session), status=status, published_at=published_at)
    db_session.add(product)
    await db_session.flush()

    assert product.status == status


async def test_published_product_needs_published_at(db_session: AsyncSession) -> None:
    db_session.add(_product(await _saved_category(db_session), status=ProductStatus.PUBLISHED))

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_unpublished_product_keeps_published_at(db_session: AsyncSession) -> None:
    first_publish = utc_now()
    product = _product(
        await _saved_category(db_session),
        status=ProductStatus.PUBLISHED,
        published_at=first_publish,
    )
    db_session.add(product)
    await db_session.flush()

    product.status = ProductStatus.DRAFT
    await db_session.flush()
    await db_session.refresh(product)

    assert product.published_at == first_publish


async def test_product_slug_unique_among_non_deleted(db_session: AsyncSession) -> None:
    category = await _saved_category(db_session)
    slug = _slug("product")
    db_session.add(_product(category, slug=slug))
    await db_session.flush()

    db_session.add(_product(category, slug=slug))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_soft_deleted_product_frees_its_slug(db_session: AsyncSession) -> None:
    category = await _saved_category(db_session)
    slug = _slug("product")
    old = _product(category, slug=slug)
    db_session.add(old)
    await db_session.flush()
    old.soft_delete()
    await db_session.flush()

    new = _product(category, slug=slug)
    db_session.add(new)
    await db_session.flush()

    assert new.id != old.id


async def test_product_audit_users_are_set_null_on_user_delete(db_session: AsyncSession) -> None:
    user = User(phone=f"+989{uuid4().int % 1_000_000_000:09d}")
    db_session.add(user)
    await db_session.flush()
    product = _product(await _saved_category(db_session), created_by=user.id, updated_by=user.id)
    db_session.add(product)
    await db_session.flush()

    await db_session.delete(user)
    await db_session.flush()
    await db_session.refresh(product)

    assert (product.created_by, product.updated_by) == (None, None)


@pytest.mark.parametrize(
    "overrides",
    [
        {"title": " "},
        {"slug": "Gold-Necklace"},
        {"slug": "x"},
        {"status": "deleted"},
        {"created_by": uuid4()},
    ],
    ids=["blank-title", "uppercase-slug", "short-slug", "unknown-status", "unknown-creator"],
)
async def test_product_constraints(db_session: AsyncSession, overrides: dict[str, object]) -> None:
    db_session.add(_product(await _saved_category(db_session), **overrides))

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_products_table_columns(db_engine: AsyncEngine) -> None:
    assert await _columns(db_engine, "products") == {
        "id",
        "category_id",
        "title",
        "slug",
        "description",
        "status",
        "published_at",
        "is_featured",
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
        "deleted_at",
    }


async def _saved_product(db_session: AsyncSession) -> Product:
    product = _product(await _saved_category(db_session))
    db_session.add(product)
    await db_session.flush()
    return product


def _sku() -> str:
    return f"SKU-{uuid4().hex[:12].upper()}"


def _variant(product: Product, **overrides: object) -> ProductVariant:
    values: dict[str, object] = {"product_id": product.id, "sku": _sku()}
    return ProductVariant(**{**values, **overrides})


async def test_variant_defaults(db_session: AsyncSession) -> None:
    variant = _variant(await _saved_product(db_session))
    db_session.add(variant)
    await db_session.flush()
    await db_session.refresh(variant)

    assert variant.is_active is False
    assert variant.is_purchasable is True
    assert variant.display_order == 0
    assert variant.deleted_at is None


async def test_product_has_many_variants_in_display_order(db_session: AsyncSession) -> None:
    product = await _saved_product(db_session)
    db_session.add_all([_variant(product, display_order=order) for order in (3, 1, 2)])
    await db_session.flush()

    orders = (
        await db_session.scalars(
            select(ProductVariant.display_order)
            .where(ProductVariant.product_id == product.id)
            .order_by(ProductVariant.display_order)
        )
    ).all()
    assert orders == [1, 2, 3]


async def test_variant_requires_existing_product(db_session: AsyncSession) -> None:
    db_session.add(ProductVariant(product_id=uuid4(), sku=_sku()))

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_referenced_product_cannot_be_hard_deleted(db_session: AsyncSession) -> None:
    product = await _saved_product(db_session)
    db_session.add(_variant(product))
    await db_session.flush()

    await db_session.delete(product)
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_sku_unique_among_non_deleted_across_products(db_session: AsyncSession) -> None:
    sku = _sku()
    db_session.add(_variant(await _saved_product(db_session), sku=sku))
    await db_session.flush()

    db_session.add(_variant(await _saved_product(db_session), sku=sku))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_soft_deleted_variant_frees_its_sku(db_session: AsyncSession) -> None:
    product = await _saved_product(db_session)
    sku = _sku()
    old = _variant(product, sku=sku)
    db_session.add(old)
    await db_session.flush()
    old.soft_delete()
    await db_session.flush()

    new = _variant(product, sku=sku)
    db_session.add(new)
    await db_session.flush()

    assert new.id != old.id


@pytest.mark.parametrize(
    "overrides",
    [
        {"sku": "sku-lower"},
        {"sku": ""},
        {"sku": " SKU-1"},
        {"sku": "SKU_1"},
        {"sku": "A" * 65},
        {"display_order": -1},
    ],
    ids=["lowercase", "empty", "untrimmed", "underscore", "too-long", "neg-order"],
)
async def test_variant_constraints(db_session: AsyncSession, overrides: dict[str, object]) -> None:
    db_session.add(_variant(await _saved_product(db_session), **overrides))

    # CHECK violations raise IntegrityError; the String(64) overflow raises DataError.
    with pytest.raises(DBAPIError):
        await db_session.flush()


async def test_variants_have_no_stock_columns(db_engine: AsyncEngine) -> None:
    # Stock lives only in InventoryItem (ADR-005); price fields came with PRC-01 (ADR-027).
    assert await _columns(db_engine, "product_variants") == {
        "id",
        "product_id",
        "sku",
        "display_order",
        "is_active",
        "is_purchasable",
        "base_price",
        "sale_price",
        "sale_start_at",
        "sale_end_at",
        "tax_enabled",
        "price_version",
        "created_at",
        "updated_at",
        "deleted_at",
    }


async def _saved_variant(db_session: AsyncSession) -> ProductVariant:
    variant = _variant(await _saved_product(db_session))
    db_session.add(variant)
    await db_session.flush()
    return variant


async def test_variant_has_one_option_per_key(db_session: AsyncSession) -> None:
    variant = await _saved_variant(db_session)
    db_session.add_all(
        [
            VariantOption(variant_id=variant.id, option_key=VariantOptionKey.COLOR, value="طلایی"),
            VariantOption(variant_id=variant.id, option_key=VariantOptionKey.SIZE, value="M"),
            VariantOption(variant_id=variant.id, option_key=VariantOptionKey.MODEL, value="A1"),
        ]
    )
    await db_session.flush()

    rows = await db_session.execute(
        select(VariantOption.option_key, VariantOption.value).where(
            VariantOption.variant_id == variant.id
        )
    )
    options = {key: value for key, value in rows}
    assert options == {"color": "طلایی", "size": "M", "model": "A1"}


async def test_variant_option_key_is_unique_per_variant(db_session: AsyncSession) -> None:
    variant = await _saved_variant(db_session)
    db_session.add(VariantOption(variant_id=variant.id, option_key="color", value="Gold"))
    await db_session.flush()

    db_session.add(VariantOption(variant_id=variant.id, option_key="color", value="Silver"))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_variant_with_options_cannot_be_hard_deleted(db_session: AsyncSession) -> None:
    variant = await _saved_variant(db_session)
    db_session.add(VariantOption(variant_id=variant.id, option_key="size", value="L"))
    await db_session.flush()

    await db_session.delete(variant)
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.parametrize(
    "overrides",
    [
        {"option_key": "material"},
        {"value": "  "},
        {"value": "x" * 51},
        {"variant_id": uuid4()},
    ],
    ids=["unknown-key", "blank-value", "long-value", "unknown-variant"],
)
async def test_variant_option_constraints(
    db_session: AsyncSession, overrides: dict[str, object]
) -> None:
    variant = await _saved_variant(db_session)
    values: dict[str, object] = {"variant_id": variant.id, "option_key": "color", "value": "Red"}
    db_session.add(VariantOption(**{**values, **overrides}))

    with pytest.raises(DBAPIError):
        await db_session.flush()


async def test_product_attributes_one_value_per_key(db_session: AsyncSession) -> None:
    product = await _saved_product(db_session)
    db_session.add_all(
        [
            ProductAttribute(
                product_id=product.id, attribute_key="material", attribute_value="Gold"
            ),
            ProductAttribute(
                product_id=product.id, attribute_key="weight", attribute_value="3g", display_order=1
            ),
        ]
    )
    await db_session.flush()

    db_session.add(
        ProductAttribute(product_id=product.id, attribute_key="material", attribute_value="Silver")
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_same_attribute_key_on_different_products(db_session: AsyncSession) -> None:
    for _ in range(2):
        product = await _saved_product(db_session)
        db_session.add(
            ProductAttribute(
                product_id=product.id, attribute_key="material", attribute_value="Gold"
            )
        )
    await db_session.flush()


@pytest.mark.parametrize(
    "overrides",
    [
        {"attribute_key": " "},
        {"attribute_value": ""},
        {"attribute_key": "k" * 51},
        {"display_order": -1},
        {"product_id": uuid4()},
    ],
    ids=["blank-key", "blank-value", "long-key", "neg-order", "unknown-product"],
)
async def test_product_attribute_constraints(
    db_session: AsyncSession, overrides: dict[str, object]
) -> None:
    product = await _saved_product(db_session)
    values: dict[str, object] = {
        "product_id": product.id,
        "attribute_key": "material",
        "attribute_value": "Gold",
    }
    db_session.add(ProductAttribute(**{**values, **overrides}))

    with pytest.raises(DBAPIError):
        await db_session.flush()
