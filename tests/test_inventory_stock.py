from __future__ import annotations

import pytest

from app.db.models import InventoryItem
from app.modules.inventory.stock import (
    StockLevel,
    StockStatus,
    free_quantity,
    max_purchasable,
    product_stock_status,
    stock_status,
    variant_level,
)

IN, LOW, OUT = StockStatus.IN_STOCK, StockStatus.LOW_STOCK, StockStatus.OUT_OF_STOCK


def _item(total: int, reserved: int = 0, threshold: int = 0) -> InventoryItem:
    return InventoryItem(
        total_quantity=total, reserved_quantity=reserved, low_stock_threshold=threshold
    )


@pytest.mark.parametrize(
    ("total", "reserved", "free"),
    [(0, 0, 0), (10, 0, 10), (10, 3, 7), (10, 10, 0), (1_000_000, 1, 999_999)],
)
def test_free_quantity(total: int, reserved: int, free: int) -> None:
    level = StockLevel(total=total, reserved=reserved, low_stock_threshold=0)

    assert free_quantity(level) == free
    assert max_purchasable(level) == free


def test_variant_without_inventory_item_has_nothing_free() -> None:
    assert free_quantity(None) == 0
    assert max_purchasable(None) == 0
    assert stock_status(None) == OUT


@pytest.mark.parametrize(
    ("total", "reserved", "threshold"),
    [(-1, 0, 0), (0, -1, 0), (5, 0, -1), (5, 6, 0)],
)
def test_inconsistent_counters_are_rejected(total: int, reserved: int, threshold: int) -> None:
    with pytest.raises(ValueError):
        StockLevel(total=total, reserved=reserved, low_stock_threshold=threshold)


@pytest.mark.parametrize(
    ("total", "reserved", "threshold", "expected"),
    [
        (0, 0, 0, OUT),
        (0, 0, 5, OUT),
        (5, 5, 3, OUT),  # everything reserved
        (1, 0, 0, IN),  # threshold 0 never yields low_stock
        (100, 99, 0, IN),
        (5, 0, 5, LOW),  # free == threshold
        (6, 0, 5, IN),  # free == threshold + 1
        (10, 6, 5, LOW),  # reservations push free under the threshold
        (1, 0, 1_000_000, LOW),
    ],
)
def test_stock_status(total: int, reserved: int, threshold: int, expected: StockStatus) -> None:
    level = StockLevel(total=total, reserved=reserved, low_stock_threshold=threshold)

    assert stock_status(level) == expected


def test_level_from_item_copies_counters() -> None:
    assert StockLevel.from_item(_item(7, 2, 3)) == StockLevel(
        total=7, reserved=2, low_stock_threshold=3
    )


def test_variant_level_sums_warehouses() -> None:
    level = variant_level([_item(5, 1, 2), _item(3, 3, 1)])

    assert level == StockLevel(total=8, reserved=4, low_stock_threshold=3)
    assert free_quantity(level) == 4
    assert stock_status(level) == IN


def test_variant_level_sums_thresholds() -> None:
    # free 4 against a summed threshold of 4; each warehouse alone would differ.
    level = variant_level([_item(3, 0, 2), _item(1, 0, 2)])

    assert stock_status(level) == LOW


def test_variant_level_without_items_is_none() -> None:
    assert variant_level([]) is None


def test_variant_level_rejects_corrupt_item() -> None:
    with pytest.raises(ValueError):
        variant_level([_item(1, 2)])


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        ([], OUT),
        ([OUT], OUT),
        ([OUT, LOW], LOW),
        ([LOW, OUT, IN], IN),
        ([IN, IN], IN),
        ([LOW, LOW], LOW),
    ],
)
def test_product_stock_status(statuses: list[StockStatus], expected: StockStatus) -> None:
    assert product_stock_status(statuses) == expected
    assert product_stock_status(iter(statuses)) == expected
