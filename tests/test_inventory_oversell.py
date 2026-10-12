"""No oversell under many concurrent writers (INV-09; ADR-029, ADR-034, ADR-036).

The pairwise races live in test_reservations.py. Here many buyers, commits, releases,
manual adjustments and the expiry sweep run at once, and the invariants are checked after
every round:

- ``0 <= reserved <= total`` and ``reserved == Σ active reservation items``;
- the movement ledger explains the counters exactly: the signed deltas of all movements
  add up to the change since the item was created (order-free, since two movements of one
  transaction may share ``created_at``).
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from conftest import Catalog, MakeAccount
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.core.errors import AppError, ErrorCode
from app.core.time import utc_now
from app.db.models import (
    InventoryItem,
    InventoryMovement,
    InventoryReservationItem,
)
from app.modules.inventory.jobs import sweep_expired_reservations
from app.modules.inventory.repository import InventoryRepository
from app.modules.inventory.reservation import (
    CommitOutcome,
    ReservationService,
    ReserveLine,
)
from app.modules.inventory.service import AdjustmentType, InventoryService

pytestmark = pytest.mark.integration

PAST = timedelta(minutes=20)  # a 15-minute reservation made this long ago has expired
URL = "/api/v1/admin/inventory"


@pytest_asyncio.fixture
async def engine(db_engine: AsyncEngine) -> AsyncIterator[AsyncEngine]:
    """Enough connections for every writer of a round to run at the same time."""
    wide = create_async_engine(db_engine.url, pool_size=25, max_overflow=0)
    yield wide
    await wide.dispose()


@dataclass(frozen=True, slots=True)
class Start:
    variant_id: UUID
    total: int


async def _stocked(catalog: Catalog, *totals: int) -> list[Start]:
    product = await catalog.product()
    variants = [await catalog.variant(product, stock=(total, 0, 0)) for total in totals]
    return [Start(variant.id, total) for variant, total in zip(variants, totals, strict=True)]


async def _reserve(
    engine: AsyncEngine, lines: Sequence[tuple[UUID, int]], *, past: bool = False
) -> UUID | None:
    """The reservation id, or None when the stock was short (all-or-nothing)."""
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session, session.begin():
            result = await ReservationService(session).reserve(
                order_id=uuid4(),
                lines=[ReserveLine(variant_id, quantity) for variant_id, quantity in lines],
                user_id=None,
                now=utc_now() - PAST if past else None,
            )
    except AppError as error:
        assert error.code == ErrorCode.INSUFFICIENT_STOCK
        return None
    return result.reservation_id


async def _commit(engine: AsyncEngine, reservation_id: UUID) -> CommitOutcome:
    async with AsyncSession(engine, expire_on_commit=False) as session, session.begin():
        return (await ReservationService(session).commit(reservation_id)).outcome


async def _release(engine: AsyncEngine, reservation_id: UUID) -> None:
    try:
        async with AsyncSession(engine) as session, session.begin():
            await ReservationService(session).release(reservation_id, reason="cancelled")
    except AppError as error:
        # Lost the race to a commit: a committed reservation is never released.
        assert error.code == ErrorCode.RESERVATION_ALREADY_CONSUMED


async def _adjust(engine: AsyncEngine, variant_id: UUID, kind: AdjustmentType, n: int) -> None:
    async with AsyncSession(engine) as session:
        try:
            await InventoryService(session, InventoryRepository(session)).adjust(
                actor_id=None, variant_id=variant_id, kind=kind, quantity=n, reason="count"
            )
        except AppError as error:
            # A decrease may not take units held by reservations.
            assert error.code == ErrorCode.INSUFFICIENT_STOCK


async def _assert_consistent(engine: AsyncEngine, starts: Sequence[Start]) -> list[int]:
    """Check every invariant; returns the free stock of each variant."""
    free: list[int] = []
    async with AsyncSession(engine) as session:
        for start in starts:
            item = (
                await session.scalars(
                    select(InventoryItem).where(InventoryItem.variant_id == start.variant_id)
                )
            ).one()
            assert 0 <= item.reserved_quantity <= item.total_quantity
            held = await session.scalar(
                select(func.coalesce(func.sum(InventoryReservationItem.quantity), 0)).where(
                    InventoryReservationItem.inventory_item_id == item.id,
                    InventoryReservationItem.status == "active",
                )
            )
            assert item.reserved_quantity == held
            moved_total, moved_reserved, count = (
                await session.execute(
                    select(
                        func.coalesce(
                            func.sum(
                                InventoryMovement.total_after - InventoryMovement.total_before
                            ),
                            0,
                        ),
                        func.coalesce(
                            func.sum(
                                InventoryMovement.reserved_after - InventoryMovement.reserved_before
                            ),
                            0,
                        ),
                        func.count(),
                    ).where(InventoryMovement.inventory_item_id == item.id)
                )
            ).one()
            assert start.total + moved_total == item.total_quantity, f"{count} movements"
            assert moved_reserved == item.reserved_quantity
            movements = await session.scalars(
                select(InventoryMovement).where(InventoryMovement.inventory_item_id == item.id)
            )
            for movement in movements:
                _assert_movement_shape(movement)
            free.append(item.total_quantity - item.reserved_quantity)
    return free


# Signed change of (total, reserved) per unit of ``quantity`` for each movement type.
_SHAPES = {
    "increase": (1, 0),
    "return": (1, 0),
    "decrease": (-1, 0),
    "reserve": (0, 1),
    "release": (0, -1),
    "commit": (-1, -1),
}


def _assert_movement_shape(movement: InventoryMovement) -> None:
    """``quantity`` is the size of the change and only the right counters move."""
    total = movement.total_after - movement.total_before
    reserved = movement.reserved_after - movement.reserved_before
    if movement.movement_type == "correction":
        assert (reserved, movement.quantity) == (0, abs(total))
        return
    shape = _SHAPES[movement.movement_type]
    assert (total, reserved) == (shape[0] * movement.quantity, shape[1] * movement.quantity)


async def _units(engine: AsyncEngine, start: Start, movement_type: str) -> int:
    async with AsyncSession(engine) as session:
        statement = (
            select(func.coalesce(func.sum(InventoryMovement.quantity), 0))
            .join(InventoryItem, InventoryItem.id == InventoryMovement.inventory_item_id)
            .where(
                InventoryItem.variant_id == start.variant_id,
                InventoryMovement.movement_type == movement_type,
            )
        )
        return int(await session.scalar(statement) or 0)


async def test_parallel_single_unit_buyers_take_exactly_the_stock(
    catalog: Catalog, engine: AsyncEngine
) -> None:
    for _ in range(3):
        [start] = await _stocked(catalog, 7)

        results = await asyncio.gather(
            *(_reserve(engine, [(start.variant_id, 1)]) for _ in range(20))
        )

        assert sum(result is not None for result in results) == 7
        assert await _assert_consistent(engine, [start]) == [0]


async def test_parallel_multi_variant_buyers_are_all_or_nothing(
    catalog: Catalog, engine: AsyncEngine
) -> None:
    starts = await _stocked(catalog, 6, 5, 4)
    ids = [start.variant_id for start in starts]
    rng = random.Random(20261012)
    baskets = []
    for _ in range(18):
        chosen = rng.sample(ids, rng.randint(1, 3))  # random order: crossing lock requests
        baskets.append([(variant_id, rng.randint(1, 2)) for variant_id in chosen])

    results = await asyncio.gather(*(_reserve(engine, basket) for basket in baskets))

    taken = {variant_id: 0 for variant_id in ids}
    for basket, result in zip(baskets, results, strict=True):
        if result is not None:
            for variant_id, quantity in basket:
                taken[variant_id] += quantity
    free = await _assert_consistent(engine, starts)
    for start, left in zip(starts, free, strict=True):
        # Every unit is either free or held by a successful basket: nothing oversold.
        assert taken[start.variant_id] + left == start.total
    assert any(result is None for result in results)
    assert any(result is not None for result in results)


async def test_mixed_writers_keep_every_invariant(catalog: Catalog, engine: AsyncEngine) -> None:
    starts = await _stocked(catalog, 8, 6)
    ids = [start.variant_id for start in starts]
    rng = random.Random(73012)
    held: list[UUID] = []
    for round_number in range(4):
        expired = [
            reservation
            for reservation in [
                await _reserve(engine, [(rng.choice(ids), 1)], past=True) for _ in range(2)
            ]
            if reservation is not None
        ]
        rng.shuffle(held)
        to_commit, to_release, held = held[:2], held[2:4], held[4:]
        writers: list[Any] = [
            *(_reserve(engine, [(rng.choice(ids), rng.randint(1, 2))]) for _ in range(6)),
            *(_commit(engine, reservation) for reservation in to_commit),
            *(_release(engine, reservation) for reservation in to_release),
            # Expired reservations: commit one (→ EXPIRED), leave the rest to the sweep.
            *(_commit(engine, reservation) for reservation in expired[:1]),
            _adjust(engine, rng.choice(ids), AdjustmentType.DECREASE, rng.randint(1, 3)),
            _adjust(engine, rng.choice(ids), AdjustmentType.INCREASE, rng.randint(1, 3)),
            sweep_expired_reservations(engine),
        ]

        results = await asyncio.gather(*writers)

        held += [result for result in results[:6] if isinstance(result, UUID)]
        for outcome in results[6 : 6 + len(to_commit)]:
            # Live holds (15-minute TTL, made seconds ago): nothing may have freed them.
            assert outcome is CommitOutcome.COMMITTED
        if expired:
            assert results[6 + len(to_commit) + len(to_release)] is CommitOutcome.EXPIRED
        assert min(await _assert_consistent(engine, starts)) >= 0, f"round {round_number}"
    for start in starts:
        # Never more sold or written off than ever was in stock.
        out = await _units(engine, start, "commit") + await _units(engine, start, "decrease")
        assert out <= start.total + await _units(engine, start, "increase")


async def test_admin_decreases_racing_buyers_never_oversell(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    catalog: Catalog,
    engine: AsyncEngine,
) -> None:
    admin = await make_account("admin")
    [start] = await _stocked(catalog, 10)

    async def decrease() -> int:
        response = await auth_client.patch(
            f"{URL}/{start.variant_id}",
            json={"adjustment_type": "decrease", "quantity": 2, "reason": "damaged"},
            headers=admin.headers,
        )
        if response.status_code == 409:
            assert response.json()["error"]["code"] == "INSUFFICIENT_STOCK"
        else:
            assert response.status_code == 200, response.text
        return response.status_code

    results = await asyncio.gather(
        *(decrease() for _ in range(6)),
        *(_reserve(engine, [(start.variant_id, 1)]) for _ in range(8)),
    )

    decreased = 2 * sum(status == 200 for status in results[:6])
    reserved = sum(result is not None for result in results[6:])
    [free] = await _assert_consistent(engine, [start])
    assert decreased + reserved + free == start.total
