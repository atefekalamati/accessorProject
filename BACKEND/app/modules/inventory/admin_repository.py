"""Admin inventory reads (INV-08, ADR-038).

Stock is computed in SQL with the same rules as ``stock.py``: only active warehouses count,
per-item ``reserved`` excludes units of expired reservations (clamped at zero, ADR-036),
and a variant without an InventoryItem is out of stock.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy import (
    ColumnElement,
    UnaryExpression,
    and_,
    case,
    exists,
    func,
    literal,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    InventoryItem,
    InventoryMovement,
    InventoryReservation,
    InventoryReservationItem,
    Product,
    ProductVariant,
    ReservationStatus,
    Warehouse,
    WarehouseStatus,
)
from app.db.models.common import not_deleted
from app.modules.inventory.holds import expired_hold_sum
from app.modules.inventory.stock import StockStatus
from app.shared.pagination import PageParams, escape_like, paginate

_ITEM: Final = (
    select(
        InventoryItem.variant_id.label("variant_id"),
        func.sum(InventoryItem.total_quantity).label("total"),
        func.sum(InventoryItem.low_stock_threshold).label("threshold"),
        func.max(InventoryItem.updated_at).label("updated_at"),
    )
    .join(Warehouse, Warehouse.id == InventoryItem.warehouse_id)
    .where(Warehouse.status == WarehouseStatus.ACTIVE)
    .group_by(InventoryItem.variant_id)
)


@dataclass(frozen=True, slots=True)
class StockColumns:
    total: ColumnElement[int]
    reserved: ColumnElement[int]
    free: ColumnElement[int]
    threshold: ColumnElement[int]
    status: ColumnElement[str]


@dataclass(frozen=True, slots=True)
class InventoryFilters:
    q: str | None = None
    product_id: UUID | None = None
    stock_status: StockStatus | None = None


def stock_columns(now: datetime) -> tuple[Any, StockColumns]:
    held = func.greatest(
        InventoryItem.reserved_quantity - expired_hold_sum(InventoryItem.id, now), 0
    )
    items = _ITEM.add_columns(func.sum(held).label("reserved")).subquery("stock")
    total = func.coalesce(items.c.total, 0)
    reserved = func.coalesce(items.c.reserved, 0)
    free = total - reserved
    threshold = func.coalesce(items.c.threshold, 0)
    status = case(
        (or_(items.c.variant_id.is_(None), free == 0), literal(StockStatus.OUT_OF_STOCK.value)),
        (free <= threshold, literal(StockStatus.LOW_STOCK.value)),
        else_=literal(StockStatus.IN_STOCK.value),
    )
    return items, StockColumns(total, reserved, free, threshold, status)


class AdminInventoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _rows(self, now: datetime) -> tuple[Any, StockColumns]:
        items, stock = stock_columns(now)
        statement = (
            select(
                ProductVariant.id.label("variant_id"),
                ProductVariant.product_id,
                Product.title.label("product_title"),
                ProductVariant.sku,
                stock.total.label("total"),
                stock.reserved.label("reserved"),
                stock.free.label("free"),
                stock.threshold.label("low_stock_threshold"),
                stock.status.label("stock_status"),
                items.c.updated_at,
            )
            .join(Product, Product.id == ProductVariant.product_id)
            .outerjoin(items, items.c.variant_id == ProductVariant.id)
            .where(not_deleted(ProductVariant), not_deleted(Product))
        )
        return statement, stock

    async def list_stock(
        self,
        filters: InventoryFilters,
        sort: str,
        params: PageParams,
        now: datetime,
    ) -> tuple[list[Any], int]:
        statement, stock = self._rows(now)
        if filters.q is not None:
            pattern = f"%{escape_like(filters.q)}%"
            statement = statement.where(
                or_(
                    ProductVariant.sku.ilike(pattern, escape="\\"),
                    Product.title.ilike(pattern, escape="\\"),
                )
            )
        if filters.product_id is not None:
            statement = statement.where(ProductVariant.product_id == filters.product_id)
        if filters.stock_status is not None:
            statement = statement.where(stock.status == filters.stock_status.value)
        order_by: dict[str, Sequence[UnaryExpression[Any]]] = {
            "sku": (ProductVariant.sku.asc(),),
            "free_asc": (stock.free.asc(),),
            "free_desc": (stock.free.desc(),),
            "updated": (statement.selected_columns.updated_at.desc().nulls_last(),),
        }
        return await paginate(
            self._session,
            statement,
            order_by[sort],
            tie_breaker=ProductVariant.id,
            params=params,
        )

    async def stock_row(self, variant_id: UUID, now: datetime) -> Any | None:
        statement, _ = self._rows(now)
        statement = statement.where(ProductVariant.id == variant_id)
        return (await self._session.execute(statement)).one_or_none()

    async def variant_exists(self, variant_id: UUID) -> bool:
        """Any variant, deleted ones included (the admin history view, ADR-030)."""
        found = await self._session.scalar(
            select(ProductVariant.id).where(ProductVariant.id == variant_id)
        )
        return found is not None

    async def history(self, variant_id: UUID, params: PageParams) -> tuple[list[Any], int]:
        statement = (
            select(InventoryMovement)
            .join(InventoryItem, InventoryItem.id == InventoryMovement.inventory_item_id)
            .where(InventoryItem.variant_id == variant_id)
        )
        rows, total = await paginate(
            self._session,
            statement,
            (InventoryMovement.created_at.desc(),),
            tie_breaker=InventoryMovement.id.desc(),
            params=params,
        )
        return [row[0] for row in rows], total


def display_status(now: datetime) -> ColumnElement[str]:
    """Stored status, with an active reservation past ``expires_at`` shown as expired."""
    return case(
        (
            and_(
                InventoryReservation.status == ReservationStatus.ACTIVE,
                InventoryReservation.expires_at <= now,
            ),
            literal(ReservationStatus.EXPIRED.value),
        ),
        else_=InventoryReservation.status,
    )


class ReservationQuery:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def page(
        self,
        *,
        status: ReservationStatus | None,
        order_id: UUID | None,
        variant_id: UUID | None,
        params: PageParams,
        now: datetime,
    ) -> tuple[list[Any], int]:
        shown = display_status(now)
        statement = select(InventoryReservation, shown.label("display_status"))
        if status is not None:
            statement = statement.where(shown == status.value)
        if order_id is not None:
            statement = statement.where(InventoryReservation.order_id == order_id)
        if variant_id is not None:
            statement = statement.where(
                exists().where(
                    InventoryReservationItem.reservation_id == InventoryReservation.id,
                    InventoryReservationItem.variant_id == variant_id,
                )
            )
        return await paginate(
            self._session,
            statement,
            (InventoryReservation.created_at.desc(),),
            tie_breaker=InventoryReservation.id.desc(),
            params=params,
        )

    async def items(self, reservation_ids: Sequence[UUID]) -> list[Any]:
        """Lines of the given reservations with their SKU, in one query."""
        if not reservation_ids:
            return []
        statement = (
            select(InventoryReservationItem, ProductVariant.sku)
            .join(ProductVariant, ProductVariant.id == InventoryReservationItem.variant_id)
            .where(InventoryReservationItem.reservation_id.in_(reservation_ids))
            .order_by(InventoryReservationItem.reservation_id, ProductVariant.sku)
        )
        return list((await self._session.execute(statement)).all())
