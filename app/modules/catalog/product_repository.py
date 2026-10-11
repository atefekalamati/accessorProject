from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    ColumnElement,
    UnaryExpression,
    delete,
    exists,
    func,
    literal,
    or_,
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.db.models import (
    Category,
    InventoryItem,
    Media,
    Product,
    ProductAttribute,
    ProductMedia,
    ProductStatus,
    ProductVariant,
    VariantOption,
    Warehouse,
    WarehouseStatus,
)
from app.db.models.common import not_deleted
from app.modules.catalog.product_query import (
    ListingFilters,
    ProductSort,
    public_products,
)
from app.shared.pagination import PageParams, paginate


@dataclass(frozen=True, slots=True)
class ProductFilters:
    q: str | None = None
    status: str | None = None
    category_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class VariantSummary:
    active_count: int
    min_price: int | None
    max_price: int | None


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _list_criteria(filters: ProductFilters) -> list[ColumnElement[bool]]:
    criteria: list[ColumnElement[bool]] = [not_deleted(Product)]
    if filters.status is not None:
        criteria.append(Product.status == filters.status)
    if filters.category_id is not None:
        criteria.append(Product.category_id == filters.category_id)
    if filters.q is not None:
        pattern = f"%{_escape_like(filters.q)}%"
        sku_match = (
            select(ProductVariant.id)
            .where(
                ProductVariant.product_id == Product.id,
                not_deleted(ProductVariant),
                ProductVariant.sku.ilike(pattern, escape="\\"),
            )
            .correlate(Product)
            .exists()
        )
        criteria.append(
            or_(
                Product.title.ilike(pattern, escape="\\"),
                Product.slug.ilike(pattern, escape="\\"),
                sku_match,
            )
        )
    return criteria


# Recursive walks stop here even if corrupt data ever contained a cycle.
_MAX_WALK = 64


class ProductRepository:
    """Product reads and writes shared by the admin (CAT-11) and public (CAT-08) services."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- public reads ------------------------------------------------------------------

    async def get_published(self, slug: str) -> Product | None:
        statement = select(Product).where(
            Product.slug == slug,
            Product.status == ProductStatus.PUBLISHED,
            not_deleted(Product),
        )
        return (await self._session.scalars(statement)).one_or_none()

    async def get_published_by_id(self, product_id: UUID) -> Product | None:
        statement = select(Product).where(
            Product.id == product_id,
            Product.status == ProductStatus.PUBLISHED,
            not_deleted(Product),
        )
        return (await self._session.scalars(statement)).one_or_none()

    async def list_public(
        self, filters: ListingFilters, sort: ProductSort, now: datetime, params: PageParams
    ) -> tuple[list[Product], int]:
        """One page of public products; card prices are computed by the service."""
        query = public_products(filters, sort, now)
        rows, total = await paginate(
            self._session,
            query.statement,
            query.order_by,
            tie_breaker=Product.id,
            params=params,
        )
        return [row[0] for row in rows], total

    async def public_variants_of(
        self, product_ids: Collection[UUID]
    ) -> dict[UUID, list[ProductVariant]]:
        """Active, priced, non-deleted variants per product, in ``display_order``."""
        variants: dict[UUID, list[ProductVariant]] = {product_id: [] for product_id in product_ids}
        if not product_ids:
            return variants
        statement = (
            select(ProductVariant)
            .where(
                ProductVariant.product_id.in_(product_ids),
                ProductVariant.is_active.is_(True),
                ProductVariant.base_price.is_not(None),
                not_deleted(ProductVariant),
            )
            .order_by(ProductVariant.display_order, ProductVariant.id)
        )
        for variant in await self._session.scalars(statement):
            variants[variant.product_id].append(variant)
        return variants

    async def category_chain(self, category_id: UUID) -> list[Category]:
        """The category and its ancestors, root first, in one recursive query."""
        chain = (
            select(Category.id, Category.parent_id, literal(1).label("level"))
            .where(Category.id == category_id)
            .cte("product_category_chain", recursive=True)
        )
        parent = aliased(Category)
        chain = chain.union_all(
            select(parent.id, parent.parent_id, chain.c.level + 1)
            .join(chain, parent.id == chain.c.parent_id)
            .where(chain.c.level < _MAX_WALK)
        )
        statement = (
            select(Category).join(chain, chain.c.id == Category.id).order_by(chain.c.level.desc())
        )
        return list((await self._session.scalars(statement)).all())

    # --- products ----------------------------------------------------------------------

    async def list_page(
        self,
        filters: ProductFilters,
        order_by: Sequence[UnaryExpression[Any]],
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[Product], int]:
        criteria = _list_criteria(filters)
        total = await self._session.scalar(
            select(func.count()).select_from(Product).where(*criteria)
        )
        statement = select(Product).where(*criteria).order_by(*order_by).offset(offset).limit(limit)
        return list((await self._session.scalars(statement)).all()), total or 0

    async def get(self, product_id: UUID) -> Product | None:
        statement = select(Product).where(Product.id == product_id, not_deleted(Product))
        return (await self._session.scalars(statement)).one_or_none()

    async def lock(self, product_id: UUID) -> Product | None:
        """Lock the product row: every product, variant and media write takes it first."""
        statement = (
            select(Product)
            .where(Product.id == product_id, not_deleted(Product))
            .with_for_update()
            # Sessions keep objects after commit (expire_on_commit=False): re-read the row.
            .execution_options(populate_existing=True)
        )
        return (await self._session.scalars(statement)).one_or_none()

    async def slug_taken(self, slug: str, *, exclude_id: UUID | None = None) -> bool:
        criteria = [Product.slug == slug, not_deleted(Product)]
        if exclude_id is not None:
            criteria.append(Product.id != exclude_id)
        return bool(await self._session.scalar(select(exists().where(*criteria))))

    async def category_exists(self, category_id: UUID) -> bool:
        statement = select(exists().where(Category.id == category_id, not_deleted(Category)))
        return bool(await self._session.scalar(statement))

    async def lock_category(self, category_id: UUID) -> bool:
        """``FOR SHARE`` on a live category: a concurrent category delete (which takes
        ``FOR UPDATE`` and then checks for products) waits for this transaction."""
        statement = (
            select(Category.id)
            .where(Category.id == category_id, not_deleted(Category))
            .with_for_update(read=True)
        )
        return await self._session.scalar(statement) is not None

    async def categories(self, category_ids: Collection[UUID]) -> dict[UUID, Category]:
        if not category_ids:
            return {}
        rows = await self._session.scalars(select(Category).where(Category.id.in_(category_ids)))
        return {category.id: category for category in rows}

    async def attributes_of(self, product_id: UUID) -> list[ProductAttribute]:
        statement = (
            select(ProductAttribute)
            .where(ProductAttribute.product_id == product_id)
            .order_by(ProductAttribute.display_order, ProductAttribute.id)
        )
        return list((await self._session.scalars(statement)).all())

    async def replace_attributes(
        self, product_id: UUID, attributes: Sequence[ProductAttribute]
    ) -> None:
        await self._session.execute(
            delete(ProductAttribute).where(ProductAttribute.product_id == product_id)
        )
        # The delete must reach the database before the inserts reuse the keys.
        await self._session.flush()
        self._session.add_all(attributes)
        await self._session.flush()

    # --- variants ----------------------------------------------------------------------

    async def variants_of(self, product_id: UUID) -> list[ProductVariant]:
        statement = (
            select(ProductVariant)
            .where(ProductVariant.product_id == product_id, not_deleted(ProductVariant))
            .order_by(ProductVariant.display_order, ProductVariant.id)
            .execution_options(populate_existing=True)
        )
        return list((await self._session.scalars(statement)).all())

    async def variant_product_id(self, variant_id: UUID) -> UUID | None:
        statement = select(ProductVariant.product_id).where(
            ProductVariant.id == variant_id, not_deleted(ProductVariant)
        )
        return await self._session.scalar(statement)

    async def get_variant(self, variant_id: UUID) -> ProductVariant | None:
        statement = (
            select(ProductVariant)
            .where(ProductVariant.id == variant_id, not_deleted(ProductVariant))
            .execution_options(populate_existing=True)
        )
        return (await self._session.scalars(statement)).one_or_none()

    async def sku_taken(self, sku: str, *, exclude_id: UUID | None = None) -> bool:
        criteria = [ProductVariant.sku == sku, not_deleted(ProductVariant)]
        if exclude_id is not None:
            criteria.append(ProductVariant.id != exclude_id)
        return bool(await self._session.scalar(select(exists().where(*criteria))))

    async def options_of(self, variant_ids: Collection[UUID]) -> dict[UUID, dict[str, str]]:
        options: dict[UUID, dict[str, str]] = {variant_id: {} for variant_id in variant_ids}
        if not variant_ids:
            return options
        rows = await self._session.execute(
            select(VariantOption.variant_id, VariantOption.option_key, VariantOption.value).where(
                VariantOption.variant_id.in_(variant_ids)
            )
        )
        for variant_id, key, value in rows:
            options[variant_id][key] = value
        return options

    async def replace_options(self, variant_id: UUID, options: dict[str, str]) -> None:
        await self._session.execute(
            delete(VariantOption).where(VariantOption.variant_id == variant_id)
        )
        await self._session.flush()
        self._session.add_all(
            VariantOption(variant_id=variant_id, option_key=key, value=value)
            for key, value in options.items()
        )
        await self._session.flush()

    async def inventory_of(self, variant_ids: Collection[UUID]) -> dict[UUID, list[InventoryItem]]:
        items: dict[UUID, list[InventoryItem]] = {variant_id: [] for variant_id in variant_ids}
        if not variant_ids:
            return items
        # Only active warehouses count (ADR-029); v1 has the single default one.
        rows = await self._session.scalars(
            select(InventoryItem)
            .join(Warehouse, Warehouse.id == InventoryItem.warehouse_id)
            .where(
                InventoryItem.variant_id.in_(variant_ids),
                Warehouse.status == WarehouseStatus.ACTIVE,
            )
        )
        for item in rows:
            items[item.variant_id].append(item)
        return items

    async def variant_summaries(self, product_ids: Collection[UUID]) -> dict[UUID, VariantSummary]:
        """Active-variant count and base-price range per product, in one query."""
        if not product_ids:
            return {}
        statement = (
            select(
                ProductVariant.product_id,
                func.count(),
                func.min(ProductVariant.base_price),
                func.max(ProductVariant.base_price),
            )
            .where(
                ProductVariant.product_id.in_(product_ids),
                ProductVariant.is_active.is_(True),
                not_deleted(ProductVariant),
            )
            .group_by(ProductVariant.product_id)
        )
        rows = await self._session.execute(statement)
        return {
            product_id: VariantSummary(int(count), low, high)
            for product_id, count, low, high in rows
        }

    async def soft_delete_variants(self, product_id: UUID) -> list[UUID]:
        variants = await self.variants_of(product_id)
        for variant in variants:
            variant.soft_delete()
        await self._session.flush()
        return [variant.id for variant in variants]

    async def detach_media(self, variant_id: UUID) -> list[UUID]:
        """Unlink images from a variant being deleted; they stay on the product."""
        result = await self._session.execute(
            update(ProductMedia)
            .where(ProductMedia.variant_id == variant_id)
            .values(variant_id=None)
            .returning(ProductMedia.id)
            .execution_options(synchronize_session="fetch")
        )
        return list(result.scalars().all())

    # --- media -------------------------------------------------------------------------

    async def media_of(self, product_id: UUID) -> list[tuple[ProductMedia, Media]]:
        statement = (
            select(ProductMedia, Media)
            .join(Media, Media.id == ProductMedia.media_id)
            .where(ProductMedia.product_id == product_id)
            .order_by(ProductMedia.display_order, ProductMedia.created_at, ProductMedia.id)
        )
        rows = await self._session.execute(statement)
        return [(product_media, media) for product_media, media in rows]

    async def get_media(
        self, product_id: UUID, media_id: UUID
    ) -> tuple[ProductMedia, Media] | None:
        statement = (
            select(ProductMedia, Media)
            .join(Media, Media.id == ProductMedia.media_id)
            .where(ProductMedia.id == media_id, ProductMedia.product_id == product_id)
            .execution_options(populate_existing=True)
        )
        row = (await self._session.execute(statement)).one_or_none()
        return None if row is None else (row[0], row[1])

    async def main_image_keys(self, product_ids: Collection[UUID]) -> dict[UUID, str]:
        if not product_ids:
            return {}
        statement = (
            select(ProductMedia.product_id, Media.storage_key)
            .join(Media, Media.id == ProductMedia.media_id)
            .where(ProductMedia.product_id.in_(product_ids), ProductMedia.is_main.is_(True))
        )
        rows = await self._session.execute(statement)
        return {product_id: key for product_id, key in rows}

    async def media_count(self, product_id: UUID) -> int:
        statement = select(func.count()).where(ProductMedia.product_id == product_id)
        return int(await self._session.scalar(statement) or 0)

    async def has_main_image(self, product_id: UUID) -> bool:
        statement = select(
            exists().where(ProductMedia.product_id == product_id, ProductMedia.is_main.is_(True))
        )
        return bool(await self._session.scalar(statement))

    async def clear_main(self, product_id: UUID) -> list[UUID]:
        """Unset the current main image; flushed before a new main is set (partial unique)."""
        result = await self._session.execute(
            update(ProductMedia)
            .where(ProductMedia.product_id == product_id, ProductMedia.is_main.is_(True))
            .values(is_main=False)
            .returning(ProductMedia.id)
            .execution_options(synchronize_session="fetch")
        )
        return list(result.scalars().all())

    async def has_active_priced_variant(self, product_id: UUID) -> bool:
        statement = select(
            exists().where(
                ProductVariant.product_id == product_id,
                ProductVariant.is_active.is_(True),
                ProductVariant.base_price > 0,
                not_deleted(ProductVariant),
            )
        )
        return bool(await self._session.scalar(statement))

    async def active_variant_count(self, product_id: UUID, *, excluding: UUID) -> int:
        statement = select(func.count()).where(
            ProductVariant.product_id == product_id,
            ProductVariant.id != excluding,
            ProductVariant.is_active.is_(True),
            not_deleted(ProductVariant),
        )
        return int(await self._session.scalar(statement) or 0)
