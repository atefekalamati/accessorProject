from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import delete, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from alembic import command
from app.db.models import (
    Category,
    InventoryItem,
    Product,
    ProductVariant,
    Warehouse,
    WarehouseStatus,
)
from app.db.models.inventory import DEFAULT_WAREHOUSE_ID
from app.shared.inventory import MAX_STOCK_QUANTITY

pytestmark = pytest.mark.integration

PRE_INVENTORY_REVISION = "20261010_0012"


def _slug(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


async def _product(session: AsyncSession) -> Product:
    category = Category(title="Category", slug=_slug("cat"))
    session.add(category)
    await session.flush()
    product = Product(category_id=category.id, title="Product", slug=_slug("prd"))
    session.add(product)
    await session.flush()
    return product


async def _variant(session: AsyncSession, product: Product | None = None) -> ProductVariant:
    product = product or await _product(session)
    variant = ProductVariant(product_id=product.id, sku=f"SKU-{uuid4().hex[:10].upper()}")
    session.add(variant)
    await session.flush()
    return variant


async def _item(session: AsyncSession, **overrides: Any) -> InventoryItem:
    variant = await _variant(session)
    fields: dict[str, Any] = {
        "warehouse_id": DEFAULT_WAREHOUSE_ID,
        "product_id": variant.product_id,
        "variant_id": variant.id,
    }
    item = InventoryItem(**(fields | overrides))
    session.add(item)
    await session.flush()
    await session.refresh(item)
    return item


# --- warehouses ----------------------------------------------------------------------


async def test_default_warehouse_row_exists(db_session: AsyncSession) -> None:
    defaults = (await db_session.scalars(select(Warehouse).where(Warehouse.is_default))).all()

    assert [warehouse.id for warehouse in defaults] == [DEFAULT_WAREHOUSE_ID]
    assert defaults[0].status == WarehouseStatus.ACTIVE
    assert defaults[0].name == "Default warehouse"


async def test_second_default_warehouse_is_rejected(db_session: AsyncSession) -> None:
    db_session.add(Warehouse(name="Second", is_default=True))

    with pytest.raises(IntegrityError, match="uq_warehouses_default"):
        await db_session.flush()


async def test_non_default_warehouses_may_coexist(db_session: AsyncSession) -> None:
    db_session.add_all([Warehouse(name="A"), Warehouse(name="B", status="inactive")])

    await db_session.flush()


@pytest.mark.parametrize(
    ("fields", "constraint"),
    [
        ({"name": "   "}, "name_not_blank"),
        ({"name": "Store", "city": " "}, "city_not_blank"),
        ({"name": "Store", "status": "closed"}, "valid_status"),
        ({"name": "Store", "status": "inactive", "is_default": True}, "default_is_active"),
    ],
)
async def test_warehouse_constraints(
    db_session: AsyncSession, fields: dict[str, Any], constraint: str
) -> None:
    if fields.get("is_default"):
        # Free the partial unique slot so only the CHECK can reject the row.
        default = await db_session.get(Warehouse, DEFAULT_WAREHOUSE_ID)
        assert default is not None
        default.is_default = False
        await db_session.flush()
    db_session.add(Warehouse(**fields))

    with pytest.raises(IntegrityError, match=f"ck_warehouses_{constraint}"):
        await db_session.flush()


async def test_warehouse_name_length_is_limited(db_session: AsyncSession) -> None:
    db_session.add(Warehouse(name="x" * 101))

    with pytest.raises(DBAPIError, match="value too long"):
        await db_session.flush()


# --- inventory items -----------------------------------------------------------------


async def test_inventory_item_defaults(db_session: AsyncSession) -> None:
    item = await _item(db_session)

    assert (item.total_quantity, item.reserved_quantity, item.low_stock_threshold) == (0, 0, 0)
    assert item.created_at is not None
    assert item.updated_at is not None


def test_variant_has_no_stock_column() -> None:
    # ADR-005: stock lives only in InventoryItem.
    columns = set(ProductVariant.__table__.columns.keys())

    assert not {"stock", "quantity", "total_quantity", "reserved_quantity"} & columns


@pytest.mark.parametrize(
    "fields",
    [
        {"total_quantity": MAX_STOCK_QUANTITY},
        {"total_quantity": 5, "reserved_quantity": 5},
        {"total_quantity": 5, "reserved_quantity": 0},
        {"low_stock_threshold": MAX_STOCK_QUANTITY},
    ],
)
async def test_valid_inventory_quantities(db_session: AsyncSession, fields: dict[str, Any]) -> None:
    item = await _item(db_session, **fields)

    assert item.id is not None


@pytest.mark.parametrize(
    ("fields", "constraint"),
    [
        # A negative total also breaks reserved <= total; either CHECK may report it.
        ({"total_quantity": -1}, "(total|reserved)_quantity_range"),
        ({"total_quantity": MAX_STOCK_QUANTITY + 1}, "total_quantity_range"),
        ({"reserved_quantity": -1}, "reserved_quantity_range"),
        ({"total_quantity": 5, "reserved_quantity": 6}, "reserved_quantity_range"),
        ({"low_stock_threshold": -1}, "low_stock_threshold_range"),
        ({"low_stock_threshold": MAX_STOCK_QUANTITY + 1}, "low_stock_threshold_range"),
    ],
)
async def test_invalid_inventory_quantities(
    db_session: AsyncSession, fields: dict[str, Any], constraint: str
) -> None:
    with pytest.raises(IntegrityError, match=f"ck_inventory_items_{constraint}"):
        await _item(db_session, **fields)


async def test_one_item_per_variant_and_warehouse(db_session: AsyncSession) -> None:
    item = await _item(db_session)
    db_session.add(
        InventoryItem(
            warehouse_id=item.warehouse_id, product_id=item.product_id, variant_id=item.variant_id
        )
    )

    with pytest.raises(IntegrityError, match="uq_inventory_items_variant_id"):
        await db_session.flush()


async def test_same_variant_in_another_warehouse(db_session: AsyncSession) -> None:
    item = await _item(db_session)
    other = Warehouse(name="Other")
    db_session.add(other)
    await db_session.flush()
    db_session.add(
        InventoryItem(warehouse_id=other.id, product_id=item.product_id, variant_id=item.variant_id)
    )

    await db_session.flush()


async def test_variant_of_another_product_is_rejected(db_session: AsyncSession) -> None:
    variant = await _variant(db_session)
    other_product = await _product(db_session)

    with pytest.raises(IntegrityError, match="fk_inventory_items_variant_id_product_variants"):
        await _item(db_session, product_id=other_product.id, variant_id=variant.id)


async def test_unknown_warehouse_is_rejected(db_session: AsyncSession) -> None:
    with pytest.raises(IntegrityError, match="fk_inventory_items_warehouse_id_warehouses"):
        await _item(db_session, warehouse_id=uuid4())


async def test_hard_delete_of_stocked_variant_is_rejected(db_session: AsyncSession) -> None:
    item = await _item(db_session)

    with pytest.raises(IntegrityError, match="fk_inventory_items_variant_id_product_variants"):
        await db_session.execute(delete(ProductVariant).where(ProductVariant.id == item.variant_id))


async def test_hard_delete_of_stocked_warehouse_is_rejected(db_session: AsyncSession) -> None:
    await _item(db_session)

    with pytest.raises(IntegrityError, match="fk_inventory_items_warehouse_id_warehouses"):
        await db_session.execute(delete(Warehouse).where(Warehouse.id == DEFAULT_WAREHOUSE_ID))


# --- migration -----------------------------------------------------------------------


async def _alembic(database_url: str, action: str, revision: str) -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    # env.py calls asyncio.run, which cannot run inside the test's event loop.
    await asyncio.to_thread(getattr(command, action), config, revision)


async def test_migration_round_trip_keeps_one_default_warehouse(
    db_engine: AsyncEngine, migrated_database: str
) -> None:
    try:
        await _alembic(migrated_database, "downgrade", PRE_INVENTORY_REVISION)
        await _alembic(migrated_database, "upgrade", "head")
        await _alembic(migrated_database, "downgrade", PRE_INVENTORY_REVISION)
        await _alembic(migrated_database, "upgrade", "head")
    finally:
        await _alembic(migrated_database, "upgrade", "head")

    async with AsyncSession(db_engine) as session:
        ids = (await session.scalars(select(Warehouse.id))).all()
    assert ids == [DEFAULT_WAREHOUSE_ID]
