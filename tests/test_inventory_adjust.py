from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import pytest
from conftest import Catalog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.errors import AppError
from app.core.time import utc_now
from app.db.models import AuditLog, InventoryItem, InventoryMovement, ProductVariant
from app.modules.inventory.repository import InventoryRepository
from app.modules.inventory.service import AdjustmentResult, AdjustmentType, InventoryService

pytestmark = pytest.mark.integration


async def _adjust(
    engine: AsyncEngine,
    variant_id: UUID,
    kind: AdjustmentType,
    quantity: Any,
    reason: Any = "stocktake",
    actor_id: UUID | None = None,
) -> AdjustmentResult:
    async with AsyncSession(engine, expire_on_commit=False) as session:
        service = InventoryService(session, InventoryRepository(session))
        return await service.adjust(
            actor_id=actor_id, variant_id=variant_id, kind=kind, quantity=quantity, reason=reason
        )


async def _movements(engine: AsyncEngine, item_id: UUID) -> list[InventoryMovement]:
    async with AsyncSession(engine) as session:
        statement = (
            select(InventoryMovement)
            .where(InventoryMovement.inventory_item_id == item_id)
            .order_by(InventoryMovement.created_at, InventoryMovement.id)
        )
        return list((await session.scalars(statement)).all())


async def _item(engine: AsyncEngine, item_id: UUID) -> InventoryItem:
    async with AsyncSession(engine) as session:
        return (
            await session.scalars(select(InventoryItem).where(InventoryItem.id == item_id))
        ).one()


async def _error(call: Any, status: int, code: str) -> None:
    with pytest.raises(AppError) as caught:
        await call
    assert (caught.value.status_code, caught.value.code) == (status, code)


async def test_first_increase_creates_the_item_with_movement_and_audit(
    catalog: Catalog, db_engine: AsyncEngine
) -> None:
    product = await catalog.product()
    variant = await catalog.variant(product)

    result = await _adjust(db_engine, variant.id, AdjustmentType.INCREASE, 7, reason=" delivery ")

    assert (result.total, result.reserved) == (7, 0)
    [movement] = await _movements(db_engine, result.inventory_item_id)
    assert movement.id == result.movement_id
    assert (movement.movement_type, movement.quantity, movement.reason) == (
        "increase",
        7,
        "delivery",
    )
    assert (movement.total_before, movement.total_after) == (0, 7)
    assert (movement.reserved_before, movement.reserved_after) == (0, 0)
    assert movement.reference_type is None and movement.created_by is None
    async with AsyncSession(db_engine) as session:
        [audit] = (
            await session.scalars(
                select(AuditLog).where(
                    AuditLog.entity_id == result.inventory_item_id,
                    AuditLog.action == "inventory.adjusted",
                )
            )
        ).all()
    assert audit.metadata_["actor"] == "system"
    diff = audit.metadata_["diff"]
    assert (diff["total_quantity"]["before"], diff["total_quantity"]["after"]) == (0, 7)
    assert diff["reason"]["after"] == "delivery"
    assert diff["movement_id"]["after"] == str(movement.id)


async def test_decrease_and_correction_respect_reserved_stock(
    catalog: Catalog, db_engine: AsyncEngine
) -> None:
    product = await catalog.product()
    variant = await catalog.variant(product, stock=(10, 4, 0))

    await _error(
        _adjust(db_engine, variant.id, AdjustmentType.DECREASE, 7), 409, "INSUFFICIENT_STOCK"
    )
    await _error(
        _adjust(db_engine, variant.id, AdjustmentType.CORRECTION, 3), 409, "INSUFFICIENT_STOCK"
    )
    decreased = await _adjust(db_engine, variant.id, AdjustmentType.DECREASE, 6)
    assert (decreased.total, decreased.reserved) == (4, 4)
    corrected = await _adjust(db_engine, variant.id, AdjustmentType.CORRECTION, 9)
    assert corrected.total == 9

    movements = await _movements(db_engine, decreased.inventory_item_id)
    # created_at can tie on Windows' coarse clock: compare without relying on row order.
    assert sorted((m.movement_type, m.quantity, m.total_after) for m in movements) == [
        ("correction", 5, 9),
        ("decrease", 6, 4),
    ]


async def test_correction_to_zero_and_noop_correction(
    catalog: Catalog, db_engine: AsyncEngine
) -> None:
    product = await catalog.product()
    variant = await catalog.variant(product, stock=(5, 0, 0))

    zero = await _adjust(db_engine, variant.id, AdjustmentType.CORRECTION, 0)
    same = await _adjust(db_engine, variant.id, AdjustmentType.CORRECTION, 0)

    assert zero.total == 0 and zero.movement_id is not None
    assert same.movement_id is None
    [movement] = await _movements(db_engine, zero.inventory_item_id)
    assert (movement.quantity, movement.total_before, movement.total_after) == (5, 5, 0)
    async with AsyncSession(db_engine) as session:
        audits = (
            await session.scalars(
                select(AuditLog).where(
                    AuditLog.entity_id == zero.inventory_item_id,
                    AuditLog.action == "inventory.adjusted",
                )
            )
        ).all()
    assert len(audits) == 1  # the no-op correction wrote none


async def test_limits_and_missing_variants(catalog: Catalog, db_engine: AsyncEngine) -> None:
    product = await catalog.product()
    variant = await catalog.variant(product, stock=(999_999, 0, 0))
    deleted = await catalog.variant(product)
    await catalog.set(ProductVariant, deleted.id, deleted_at=utc_now())

    await _error(
        _adjust(db_engine, variant.id, AdjustmentType.INCREASE, 2), 422, "BUSINESS_RULE_VIOLATION"
    )
    for variant_id in (deleted.id, uuid4()):
        await _error(_adjust(db_engine, variant_id, AdjustmentType.INCREASE, 1), 404, "NOT_FOUND")
    assert (await _item(db_engine, (await _adjust(
        db_engine, variant.id, AdjustmentType.INCREASE, 1
    )).inventory_item_id)).total_quantity == 1_000_000  # fmt: skip


@pytest.mark.parametrize(
    ("kind", "quantity", "reason"),
    [
        (AdjustmentType.INCREASE, 0, "x"),
        (AdjustmentType.DECREASE, -1, "x"),
        (AdjustmentType.INCREASE, True, "x"),
        (AdjustmentType.INCREASE, 1.5, "x"),
        (AdjustmentType.INCREASE, "3", "x"),
        (AdjustmentType.CORRECTION, 1_000_001, "x"),
        (AdjustmentType.INCREASE, 1, "   "),
        (AdjustmentType.INCREASE, 1, "r" * 501),
        (AdjustmentType.INCREASE, 1, None),
    ],
)
async def test_invalid_input_is_400(
    catalog: Catalog, db_engine: AsyncEngine, kind: AdjustmentType, quantity: Any, reason: Any
) -> None:
    product = await catalog.product()
    variant = await catalog.variant(product)

    await _error(_adjust(db_engine, variant.id, kind, quantity, reason), 400, "VALIDATION_ERROR")


async def test_concurrent_adjustments_are_serialized(
    catalog: Catalog, db_engine: AsyncEngine
) -> None:
    product = await catalog.product()
    variant = await catalog.variant(product)  # no item yet: the first ones race to create it

    results = await asyncio.gather(
        *(_adjust(db_engine, variant.id, AdjustmentType.INCREASE, 1) for _ in range(8))
    )

    item_ids = {result.inventory_item_id for result in results}
    assert len(item_ids) == 1
    [item_id] = item_ids
    assert (await _item(db_engine, item_id)).total_quantity == 8
    movements = await _movements(db_engine, item_id)
    assert len(movements) == 8
    # Each movement starts where another one ended: no lost update.
    assert sorted(m.total_before for m in movements) == list(range(8))
    assert sorted(m.total_after for m in movements) == list(range(1, 9))


@pytest.mark.parametrize(
    "fields",
    [
        # increase must add exactly quantity
        {"movement_type": "increase", "quantity": 2, "total_after": 4},
        # manual changes need a reason
        {"movement_type": "decrease", "quantity": 1, "total_after": 2, "reason": None},
        # reservation flows need a reference
        {"movement_type": "reserve", "quantity": 1, "reserved_after": 1},
        {"movement_type": "increase", "quantity": 1, "total_after": 4, "reference_type": "x",
         "reference_id": uuid4()},
    ],
)  # fmt: skip
async def test_database_rejects_inconsistent_movements(
    catalog: Catalog, db_engine: AsyncEngine, fields: dict[str, Any]
) -> None:
    product = await catalog.product()
    variant = await catalog.variant(product, stock=(3, 0, 0))
    async with AsyncSession(db_engine) as session:
        item_id = (
            await session.scalars(
                select(InventoryItem.id).where(InventoryItem.variant_id == variant.id)
            )
        ).one()
    values: dict[str, Any] = {
        "inventory_item_id": item_id,
        "total_before": 3,
        "total_after": 3,
        "reserved_before": 0,
        "reserved_after": 0,
        "reason": "test",
    } | fields

    with pytest.raises(IntegrityError):
        async with AsyncSession(db_engine) as session, session.begin():
            session.add(InventoryMovement(**values))
