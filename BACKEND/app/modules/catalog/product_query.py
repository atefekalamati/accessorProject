"""SQL for the public product listing (CAT-07, PRD «دسته‌بندی محصولات» ✓, ADR-032).

Filtering and sorting by price happen in the database, so the sale-window rule of
``app.modules.pricing.calculator.unit_price`` is mirrored here as a SQL expression:
the sale price applies inside the half-open window ``[sale_start_at, sale_end_at)``.
Card prices themselves are still computed in Python with ``unit_price``; tests check that
both agree.

A product's listing price is the lowest final price among its *public* variants:
active, priced and not deleted.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, and_, case, exists, func, or_, select
from sqlalchemy.orm import aliased

from app.db.models import (
    InventoryItem,
    Product,
    ProductAttribute,
    ProductStatus,
    ProductVariant,
    VariantOption,
    VariantOptionKey,
    Warehouse,
    WarehouseStatus,
)
from app.db.models.common import not_deleted
from app.modules.inventory.holds import expired_hold_sum
from app.modules.orders.sales import units_sold_by_product
from app.shared.pagination import AnySelect

_OPTION_KEYS = frozenset(VariantOptionKey)


class ProductSort(StrEnum):
    NEWEST = "newest"
    PRICE_ASC = "price_asc"
    PRICE_DESC = "price_desc"
    DISCOUNT_DESC = "discount_desc"
    # Units in paid orders (CAT-17, ADR-047); ties by id.
    BEST_SELLING = "best_selling"


PRODUCT_SORTS: Mapping[str, ProductSort] = {sort.value: sort for sort in ProductSort}


@dataclass(frozen=True, slots=True)
class ListingFilters:
    category_id: UUID | None = None
    min_price: int | None = None
    max_price: int | None = None
    in_stock: bool = False
    has_discount: bool = False
    # Filter key (variant option key or product attribute key) → accepted values.
    # Values of one key are OR-ed; different keys are AND-ed.
    values: Mapping[str, frozenset[str]] = field(default_factory=dict)


def _public_variant(variant: Any) -> ColumnElement[bool]:
    return and_(
        variant.is_active.is_(True),
        variant.base_price.is_not(None),
        variant.deleted_at.is_(None),
    )


def final_price(now: datetime) -> ColumnElement[int]:
    """SQL twin of ``unit_price(...).final`` for a ``ProductVariant`` row at ``now``."""
    in_window = and_(
        ProductVariant.sale_price.is_not(None),
        or_(ProductVariant.sale_start_at.is_(None), ProductVariant.sale_start_at <= now),
        or_(ProductVariant.sale_end_at.is_(None), now < ProductVariant.sale_end_at),
    )
    return case((in_window, ProductVariant.sale_price), else_=ProductVariant.base_price)


def _has_free_stock(now: datetime) -> ColumnElement[bool]:
    variant = aliased(ProductVariant)
    return exists(
        select(InventoryItem.id)
        .join(variant, variant.id == InventoryItem.variant_id)
        .join(Warehouse, Warehouse.id == InventoryItem.warehouse_id)
        .where(
            variant.product_id == Product.id,
            _public_variant(variant),
            # Only active warehouses count (ADR-029). free = total − reserved, where
            # units of expired reservations are not reserved any more (ADR-036).
            Warehouse.status == WarehouseStatus.ACTIVE,
            InventoryItem.total_quantity
            > InventoryItem.reserved_quantity - expired_hold_sum(InventoryItem.id, now),
        )
        .correlate(Product)
    )


def _has_value(key: str, values: frozenset[str]) -> ColumnElement[bool]:
    if key in _OPTION_KEYS:
        variant = aliased(ProductVariant)
        return exists(
            select(VariantOption.id)
            .join(variant, variant.id == VariantOption.variant_id)
            .where(
                variant.product_id == Product.id,
                _public_variant(variant),
                VariantOption.option_key == key,
                VariantOption.value.in_(sorted(values)),
            )
            .correlate(Product)
        )
    return exists(
        select(ProductAttribute.id)
        .where(
            ProductAttribute.product_id == Product.id,
            ProductAttribute.attribute_key == key,
            ProductAttribute.attribute_value.in_(sorted(values)),
        )
        .correlate(Product)
    )


@dataclass(frozen=True, slots=True)
class ListingQuery:
    statement: AnySelect
    order_by: list[ColumnElement[Any]]


def public_products(filters: ListingFilters, sort: ProductSort, now: datetime) -> ListingQuery:
    """``(Product, min_price, max_price, max_discount_percent)`` rows, one per product.

    Grouped over the product's public variants, so a product without one never appears.
    """
    final = final_price(now)
    min_price = func.min(final)
    max_price = func.max(final)
    discount = ProductVariant.base_price - final
    # Integer division of non-negative numbers floors, like ``unit_price``.
    max_discount_percent = func.max(discount * 100 // ProductVariant.base_price)

    criteria: list[ColumnElement[bool]] = [
        Product.status == ProductStatus.PUBLISHED,
        not_deleted(Product),
        _public_variant(ProductVariant),
    ]
    if filters.category_id is not None:
        criteria.append(Product.category_id == filters.category_id)
    if filters.in_stock:
        criteria.append(_has_free_stock(now))
    for key, values in sorted(filters.values.items()):
        criteria.append(_has_value(key, values))

    having: list[ColumnElement[bool]] = []
    if filters.min_price is not None:
        having.append(min_price >= filters.min_price)
    if filters.max_price is not None:
        having.append(min_price <= filters.max_price)
    if filters.has_discount:
        having.append(func.max(discount) > 0)

    statement = (
        select(
            Product,
            min_price.label("min_price"),
            max_price.label("max_price"),
            max_discount_percent.label("max_discount_percent"),
        )
        .join(ProductVariant, ProductVariant.product_id == Product.id)
        .where(*criteria)
        .group_by(Product.id)
    )
    if having:
        statement = statement.having(*having)

    units_sold: ColumnElement[Any] | None = None
    if sort is ProductSort.BEST_SELLING:
        # One pre-aggregated subquery joined once, not a correlated count per product.
        sold = units_sold_by_product()
        statement = statement.outerjoin(sold, sold.c.product_id == Product.id)
        units_sold = func.coalesce(func.max(sold.c.units), 0)

    newest = Product.published_at.desc()
    order_by: dict[ProductSort, list[ColumnElement[Any]]] = {
        ProductSort.NEWEST: [newest],
        ProductSort.PRICE_ASC: [min_price.asc()],
        ProductSort.PRICE_DESC: [min_price.desc()],
        ProductSort.DISCOUNT_DESC: [max_discount_percent.desc(), newest],
    }
    if units_sold is not None:
        order_by[ProductSort.BEST_SELLING] = [units_sold.desc()]
    return ListingQuery(statement=statement, order_by=order_by[sort])


def price_bounds(category_id: UUID, now: datetime) -> AnySelect:
    """Lowest and highest listing price among the category's public products."""
    listed = public_products(
        ListingFilters(category_id=category_id), ProductSort.NEWEST, now
    ).statement.subquery()
    return select(func.min(listed.c.min_price), func.max(listed.c.min_price))
