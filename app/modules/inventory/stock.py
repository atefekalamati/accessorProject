"""Pure free-stock and stock-status rules (INV-03, ADR-005, ADR-007, ADR-029).

No database access: callers load the InventoryItem rows (active warehouses only) and pass
their counters. ``reserved`` is the active-reservation counter; write paths release expired
reservations under lock before calling these functions (ADR-029).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from app.db.models import InventoryItem


class StockStatus(StrEnum):
    IN_STOCK = "in_stock"
    LOW_STOCK = "low_stock"
    OUT_OF_STOCK = "out_of_stock"


# Best first: a product shows the best status among its variants.
_STATUS_RANK = {StockStatus.IN_STOCK: 0, StockStatus.LOW_STOCK: 1, StockStatus.OUT_OF_STOCK: 2}


@dataclass(frozen=True, slots=True)
class StockLevel:
    total: int
    reserved: int
    low_stock_threshold: int

    def __post_init__(self) -> None:
        if min(self.total, self.reserved, self.low_stock_threshold) < 0:
            raise ValueError("stock counters must not be negative")
        if self.reserved > self.total:
            raise ValueError("reserved stock exceeds total stock")

    @classmethod
    def from_item(cls, item: InventoryItem) -> StockLevel:
        return cls(
            total=item.total_quantity,
            reserved=item.reserved_quantity,
            low_stock_threshold=item.low_stock_threshold,
        )


def variant_level(items: Iterable[InventoryItem]) -> StockLevel | None:
    """Sum a variant's items across warehouses; ``None`` when it has no InventoryItem."""
    levels = [StockLevel.from_item(item) for item in items]
    if not levels:
        return None
    return StockLevel(
        total=sum(level.total for level in levels),
        reserved=sum(level.reserved for level in levels),
        low_stock_threshold=sum(level.low_stock_threshold for level in levels),
    )


def free_quantity(level: StockLevel | None) -> int:
    """``free = total − active reservations``; a variant without stock has none."""
    if level is None:
        return 0
    return level.total - level.reserved


def max_purchasable(level: StockLevel | None) -> int:
    """Most units one purchase may take (internal/admin only; never in public responses)."""
    return free_quantity(level)


def stock_status(level: StockLevel | None) -> StockStatus:
    free = free_quantity(level)
    if level is None or free == 0:
        return StockStatus.OUT_OF_STOCK
    if free <= level.low_stock_threshold:
        return StockStatus.LOW_STOCK
    return StockStatus.IN_STOCK


def product_stock_status(statuses: Iterable[StockStatus]) -> StockStatus:
    """Best status among the variants the caller counts; no variants → out of stock."""
    return min(statuses, key=_STATUS_RANK.__getitem__, default=StockStatus.OUT_OF_STOCK)
