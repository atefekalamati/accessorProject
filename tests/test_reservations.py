"""Reservations: reserve, commit, release, expiry without the job, concurrency
(INV-04, INV-05, ADR-036)."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from conftest import Catalog
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.errors import AppError
from app.core.time import utc_now
from app.db.models import (
    AuditLog,
    Category,
    InventoryItem,
    InventoryMovement,
    InventoryReservation,
    InventoryReservationItem,
    Product,
    ProductStatus,
    ProductVariant,
)
from app.modules.inventory.repository import InventoryRepository
from app.modules.inventory.reservation import (
    RESERVATION_TTL,
    CommitOutcome,
    CommitResult,
    ReleaseOutcome,
    ReleaseResult,
    ReservationResult,
    ReservationService,
    ReserveLine,
)
from app.modules.inventory.service import AdjustmentType, InventoryService

pytestmark = pytest.mark.integration

PAST = timedelta(minutes=20)  # long enough for a 15-minute reservation to have expired


async def _reserve(
    engine: AsyncEngine,
    lines: Sequence[tuple[UUID, Any]],
    *,
    order_id: UUID | None = None,
    now: datetime | None = None,
) -> ReservationResult:
    async with AsyncSession(engine, expire_on_commit=False) as session, session.begin():
        return await ReservationService(session).reserve(
            order_id=order_id or uuid4(),
            lines=[ReserveLine(variant_id, quantity) for variant_id, quantity in lines],
            user_id=None,
            now=now,
        )


async def _error(call: Any, status: int, code: str) -> AppError:
    with pytest.raises(AppError) as caught:
        await call
    assert (caught.value.status_code, caught.value.code) == (status, code)
    return caught.value


async def _item(engine: AsyncEngine, variant_id: UUID) -> InventoryItem:
    async with AsyncSession(engine) as session:
        statement = select(InventoryItem).where(InventoryItem.variant_id == variant_id)
        return (await session.scalars(statement)).one()


async def _assert_invariant(engine: AsyncEngine, variant_ids: Sequence[UUID]) -> None:
    """reserved == Σ active reservation items; closed reservations hold no active items."""
    async with AsyncSession(engine) as session:
        for variant_id in variant_ids:
            item = (
                await session.scalars(
                    select(InventoryItem).where(InventoryItem.variant_id == variant_id)
                )
            ).one()
            held = await session.scalar(
                select(func.coalesce(func.sum(InventoryReservationItem.quantity), 0)).where(
                    InventoryReservationItem.inventory_item_id == item.id,
                    InventoryReservationItem.status == "active",
                )
            )
            assert item.reserved_quantity == held
            assert 0 <= item.reserved_quantity <= item.total_quantity
        stray = await session.scalar(
            select(func.count())
            .select_from(InventoryReservationItem)
            .join(
                InventoryReservation,
                InventoryReservation.id == InventoryReservationItem.reservation_id,
            )
            .where(
                InventoryReservation.status != "active",
                InventoryReservationItem.status == "active",
            )
        )
        assert stray == 0


async def _stocked(catalog: Catalog, *stocks: int) -> list[ProductVariant]:
    product = await catalog.product()
    return [await catalog.variant(product, stock=(total, 0, 0)) for total in stocks]


# --- reserve -------------------------------------------------------------------------


async def test_reserve_holds_stock_with_movement_and_audit(
    catalog: Catalog, db_engine: AsyncEngine
) -> None:
    first, second = await _stocked(catalog, 5, 3)
    now = utc_now()
    order_id = uuid4()

    result = await _reserve(
        db_engine, [(second.id, 1), (first.id, 2), (first.id, 1)], order_id=order_id, now=now
    )

    assert result.created and result.expires_at == now + RESERVATION_TTL
    assert (await _item(db_engine, first.id)).reserved_quantity == 3  # duplicate lines merged
    assert (await _item(db_engine, second.id)).reserved_quantity == 1
    async with AsyncSession(db_engine) as session:
        reservation = await session.get(InventoryReservation, result.reservation_id)
        assert reservation is not None
        assert (reservation.order_id, reservation.status) == (order_id, "active")
        movements = (
            await session.scalars(
                select(InventoryMovement).where(
                    InventoryMovement.reference_id == result.reservation_id
                )
            )
        ).all()
        assert sorted((m.movement_type, m.quantity) for m in movements) == [
            ("reserve", 1),
            ("reserve", 3),
        ]
        assert {m.reference_type for m in movements} == {"reservation"}
        [audit] = (
            await session.scalars(
                select(AuditLog).where(
                    AuditLog.entity_id == result.reservation_id,
                    AuditLog.action == "reservation.created",
                )
            )
        ).all()
    assert audit.metadata_["actor"] == "system"
    await _assert_invariant(db_engine, [first.id, second.id])


async def test_reserve_is_idempotent_per_order(catalog: Catalog, db_engine: AsyncEngine) -> None:
    [variant] = await _stocked(catalog, 5)
    order_id = uuid4()

    first = await _reserve(db_engine, [(variant.id, 2)], order_id=order_id)
    again = await _reserve(db_engine, [(variant.id, 1), (variant.id, 1)], order_id=order_id)

    assert (again.reservation_id, again.created) == (first.reservation_id, False)
    assert (await _item(db_engine, variant.id)).reserved_quantity == 2
    await _error(_reserve(db_engine, [(variant.id, 3)], order_id=order_id), 409, "CONFLICT")
    await _assert_invariant(db_engine, [variant.id])


async def test_reserve_is_all_or_nothing(catalog: Catalog, db_engine: AsyncEngine) -> None:
    enough, short = await _stocked(catalog, 5, 1)
    no_item = await catalog.variant(await catalog.product())
    order_id = uuid4()

    error = await _error(
        _reserve(db_engine, [(enough.id, 2), (short.id, 2)], order_id=order_id),
        409,
        "INSUFFICIENT_STOCK",
    )
    assert error.details == [{"variant_id": str(short.id), "type": "insufficient_stock"}]
    # A variant without an InventoryItem has no stock; none is created for it.
    await _error(_reserve(db_engine, [(no_item.id, 1)]), 409, "INSUFFICIENT_STOCK")

    assert (await _item(db_engine, enough.id)).reserved_quantity == 0
    async with AsyncSession(db_engine) as session:
        count = await session.scalar(
            select(func.count())
            .select_from(InventoryReservation)
            .where(InventoryReservation.order_id == order_id)
        )
        items = await session.scalar(
            select(func.count())
            .select_from(InventoryItem)
            .where(InventoryItem.variant_id == no_item.id)
        )
    assert (count, items) == (0, 0)


async def test_unsellable_variants_are_422(catalog: Catalog, db_engine: AsyncEngine) -> None:
    product = await catalog.product()
    inactive = await catalog.variant(product, stock=(5, 0, 0), is_active=False)
    blocked = await catalog.variant(product, stock=(5, 0, 0), is_purchasable=False)
    deleted = await catalog.variant(product, stock=(5, 0, 0))
    await catalog.set(ProductVariant, deleted.id, deleted_at=utc_now())
    draft = await catalog.product(status=ProductStatus.DRAFT)
    of_draft = await catalog.variant(draft, stock=(5, 0, 0))
    gone = await catalog.product()
    of_gone = await catalog.variant(gone, stock=(5, 0, 0))
    await catalog.set(Product, gone.id, deleted_at=utc_now())

    for variant_id in (inactive.id, blocked.id, deleted.id, of_draft.id, of_gone.id, uuid4()):
        error = await _error(_reserve(db_engine, [(variant_id, 1)]), 422, "BUSINESS_RULE_VIOLATION")
        assert error.details == [{"variant_id": str(variant_id), "type": "not_purchasable"}]


@pytest.mark.parametrize(
    "lines",
    [[], [(None, 1)], [("v", 0)], [("v", True)], [("v", 1.0)], [("v", 600_000), ("v", 500_000)]],
)
async def test_invalid_lines_are_400(
    catalog: Catalog, db_engine: AsyncEngine, lines: list[tuple[Any, Any]]
) -> None:
    [variant] = await _stocked(catalog, 5)
    resolved = [(variant.id if v == "v" else v, q) for v, q in lines]

    await _error(_reserve(db_engine, resolved), 400, "VALIDATION_ERROR")


async def test_reserve_needs_the_callers_transaction(db_engine: AsyncEngine) -> None:
    async with AsyncSession(db_engine) as session:
        with pytest.raises(RuntimeError):
            await ReservationService(session).reserve(
                order_id=uuid4(), lines=[ReserveLine(uuid4(), 1)], user_id=None
            )


async def test_callers_rollback_leaves_nothing(catalog: Catalog, db_engine: AsyncEngine) -> None:
    [variant] = await _stocked(catalog, 5)

    with pytest.raises(LookupError):
        async with AsyncSession(db_engine) as session, session.begin():
            await ReservationService(session).reserve(
                order_id=uuid4(), lines=[ReserveLine(variant.id, 2)], user_id=None
            )
            raise LookupError  # e.g. the order insert failed after reserving

    assert (await _item(db_engine, variant.id)).reserved_quantity == 0
    await _assert_invariant(db_engine, [variant.id])


async def test_committed_order_cannot_reserve_again(
    catalog: Catalog, db_engine: AsyncEngine
) -> None:
    [variant] = await _stocked(catalog, 5)
    order_id = uuid4()
    result = await _reserve(db_engine, [(variant.id, 1)], order_id=order_id)
    await _commit(db_engine, result.reservation_id)

    await _error(
        _reserve(db_engine, [(variant.id, 1)], order_id=order_id),
        409,
        "RESERVATION_ALREADY_CONSUMED",
    )


# --- expiry without the job ----------------------------------------------------------


async def test_expired_holds_are_released_by_the_next_reserve(
    catalog: Catalog, db_engine: AsyncEngine
) -> None:
    [variant] = await _stocked(catalog, 1)
    now = utc_now()
    old = await _reserve(db_engine, [(variant.id, 1)], now=now - PAST)

    new = await _reserve(db_engine, [(variant.id, 1)], now=now)

    assert new.created and (await _item(db_engine, variant.id)).reserved_quantity == 1
    async with AsyncSession(db_engine) as session:
        [released] = (
            await session.scalars(
                select(InventoryMovement).where(
                    InventoryMovement.reference_id == old.reservation_id,
                    InventoryMovement.movement_type == "release",
                )
            )
        ).all()
    assert (released.reason, released.created_by) == ("expired", None)
    await _assert_invariant(db_engine, [variant.id])


async def test_reservation_is_inactive_at_its_expiry_moment(
    catalog: Catalog, db_engine: AsyncEngine
) -> None:
    [variant] = await _stocked(catalog, 1)
    first = await _reserve(db_engine, [(variant.id, 1)])

    # Exactly at expires_at the unit is free again: [created, expires_at).
    second = await _reserve(db_engine, [(variant.id, 1)], now=first.expires_at)
    assert second.created
    # One microsecond earlier it still held the unit.
    [other] = await _stocked(catalog, 1)
    held = await _reserve(db_engine, [(other.id, 1)])
    await _error(
        _reserve(db_engine, [(other.id, 1)], now=held.expires_at - timedelta(microseconds=1)),
        409,
        "INSUFFICIENT_STOCK",
    )


async def test_same_order_after_expiry_gets_a_new_reservation(
    catalog: Catalog, db_engine: AsyncEngine
) -> None:
    [variant] = await _stocked(catalog, 2)
    order_id = uuid4()
    now = utc_now()
    old = await _reserve(db_engine, [(variant.id, 2)], order_id=order_id, now=now - PAST)

    new = await _reserve(db_engine, [(variant.id, 2)], order_id=order_id, now=now)

    assert new.created and new.reservation_id != old.reservation_id
    async with AsyncSession(db_engine) as session:
        previous = await session.get(InventoryReservation, old.reservation_id)
        assert previous is not None and previous.status == "expired"
        expired_audits = await session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.entity_id == old.reservation_id, AuditLog.action == "reservation.expired"
            )
        )
    assert expired_audits == 1
    assert (await _item(db_engine, variant.id)).reserved_quantity == 2
    await _assert_invariant(db_engine, [variant.id])


async def test_public_stock_ignores_expired_unswept_reservations(
    auth_client: AsyncClient, catalog: Catalog, db_engine: AsyncEngine
) -> None:
    product = await catalog.product()
    variant = await catalog.variant(product, stock=(1, 0, 0))
    await _reserve(db_engine, [(variant.id, 1)], now=utc_now() - PAST)
    assert (await _item(db_engine, variant.id)).reserved_quantity == 1  # not cleaned up yet

    availability = (await auth_client.get(f"/api/v1/products/{product.id}/availability")).json()
    detail = (await auth_client.get(f"/api/v1/products/{product.slug}")).json()
    listing = await auth_client.get(
        f"/api/v1/categories/{(await _category_slug(db_engine, product.id))}/products",
        params={"in_stock": "true"},
    )

    assert availability["availability"] == "in_stock"
    assert detail["variants"][0]["purchasable"] is True
    assert [item["id"] for item in listing.json()["items"]] == [str(product.id)]

    # A live reservation does hold the unit.
    await _reserve(db_engine, [(variant.id, 1)])
    availability = (await auth_client.get(f"/api/v1/products/{product.id}/availability")).json()
    assert availability["availability"] == "out_of_stock"
    listing = await auth_client.get(
        f"/api/v1/categories/{(await _category_slug(db_engine, product.id))}/products",
        params={"in_stock": "true"},
    )
    assert listing.json()["items"] == []


async def _category_slug(engine: AsyncEngine, product_id: UUID) -> str:
    async with AsyncSession(engine) as session:
        slug: str = (
            await session.scalars(
                select(Category.slug)
                .join(Product, Product.category_id == Category.id)
                .where(Product.id == product_id)
            )
        ).one()
        return slug


async def test_manual_decrease_ignores_expired_holds(
    catalog: Catalog, db_engine: AsyncEngine
) -> None:
    [variant] = await _stocked(catalog, 2)
    await _reserve(db_engine, [(variant.id, 2)], now=utc_now() - PAST)

    async with AsyncSession(db_engine) as session:
        result = await InventoryService(session, InventoryRepository(session)).adjust(
            actor_id=None,
            variant_id=variant.id,
            kind=AdjustmentType.DECREASE,
            quantity=2,
            reason="damaged",
        )

    assert (result.total, result.reserved) == (0, 0)
    await _assert_invariant(db_engine, [variant.id])


# --- concurrency ---------------------------------------------------------------------


async def test_parallel_buyers_for_the_last_unit(catalog: Catalog, db_engine: AsyncEngine) -> None:
    [variant] = await _stocked(catalog, 1)

    results = await asyncio.gather(
        *(_reserve(db_engine, [(variant.id, 1)]) for _ in range(10)), return_exceptions=True
    )

    winners = [result for result in results if isinstance(result, ReservationResult)]
    losers = [result for result in results if isinstance(result, AppError)]
    assert len(winners) == 1 and len(losers) == 9
    assert {error.code for error in losers} == {"INSUFFICIENT_STOCK"}
    assert (await _item(db_engine, variant.id)).reserved_quantity == 1
    await _assert_invariant(db_engine, [variant.id])


async def test_crossing_multi_variant_orders_do_not_deadlock(
    catalog: Catalog, db_engine: AsyncEngine
) -> None:
    first, second = await _stocked(catalog, 10, 10)
    forward = [(first.id, 1), (second.id, 1)]
    backward = [(second.id, 1), (first.id, 1)]

    results = await asyncio.gather(
        *(_reserve(db_engine, forward if index % 2 else backward) for index in range(8))
    )

    assert all(result.created for result in results)
    assert (await _item(db_engine, first.id)).reserved_quantity == 8
    await _assert_invariant(db_engine, [first.id, second.id])


async def test_concurrent_calls_for_one_order_make_one_reservation(
    catalog: Catalog, db_engine: AsyncEngine
) -> None:
    first, second = await _stocked(catalog, 5, 5)
    order_id = uuid4()

    results = await asyncio.gather(
        _reserve(db_engine, [(first.id, 1)], order_id=order_id),
        _reserve(db_engine, [(second.id, 1)], order_id=order_id),
        return_exceptions=True,
    )

    created = [result for result in results if isinstance(result, ReservationResult)]
    conflicts = [result for result in results if isinstance(result, AppError)]
    assert len(created) == 1 and [error.code for error in conflicts] == ["CONFLICT"]
    async with AsyncSession(db_engine) as session:
        count = await session.scalar(
            select(func.count())
            .select_from(InventoryReservation)
            .where(InventoryReservation.order_id == order_id)
        )
    assert count == 1
    await _assert_invariant(db_engine, [first.id, second.id])


async def test_partly_released_expired_reservation_is_closed_on_re_reserve(
    catalog: Catalog, db_engine: AsyncEngine
) -> None:
    first, second = await _stocked(catalog, 1, 1)
    order_id = uuid4()
    now = utc_now()
    old = await _reserve(
        db_engine, [(first.id, 1), (second.id, 1)], order_id=order_id, now=now - PAST
    )
    # Another order takes the first unit: only that item of the old reservation is released.
    await _reserve(db_engine, [(first.id, 1)], now=now)

    renewed = await _reserve(db_engine, [(second.id, 1)], order_id=order_id, now=now)

    assert renewed.created
    async with AsyncSession(db_engine) as session:
        previous = await session.get(InventoryReservation, old.reservation_id)
        assert previous is not None and previous.status == "expired"
    assert (await _item(db_engine, first.id)).reserved_quantity == 1
    assert (await _item(db_engine, second.id)).reserved_quantity == 1
    await _assert_invariant(db_engine, [first.id, second.id])


async def test_reserve_racing_a_manual_decrease_never_oversells(
    catalog: Catalog, db_engine: AsyncEngine
) -> None:
    [variant] = await _stocked(catalog, 3)

    async def decrease() -> object:
        async with AsyncSession(db_engine) as session:
            return await InventoryService(session, InventoryRepository(session)).adjust(
                actor_id=None,
                variant_id=variant.id,
                kind=AdjustmentType.DECREASE,
                quantity=2,
                reason="damaged",
            )

    results = await asyncio.gather(
        _reserve(db_engine, [(variant.id, 2)]), decrease(), return_exceptions=True
    )

    # Whichever ran second found only one unit left and failed with 409.
    failures = [result for result in results if isinstance(result, AppError)]
    assert len(failures) == 1 and failures[0].code == "INSUFFICIENT_STOCK"
    item = await _item(db_engine, variant.id)
    assert item.total_quantity - item.reserved_quantity >= 0
    await _assert_invariant(db_engine, [variant.id])


# --- commit and release (INV-05) -----------------------------------------------------


async def _commit(
    engine: AsyncEngine, reservation_id: UUID, *, now: datetime | None = None
) -> CommitResult:
    async with AsyncSession(engine, expire_on_commit=False) as session, session.begin():
        return await ReservationService(session).commit(reservation_id, now=now)


async def _release(
    engine: AsyncEngine,
    reservation_id: UUID,
    *,
    reason: Any = "payment_failed",
    now: datetime | None = None,
) -> ReleaseResult:
    async with AsyncSession(engine, expire_on_commit=False) as session, session.begin():
        return await ReservationService(session).release(reservation_id, reason=reason, now=now)


async def _raise_for(result: CommitResult) -> None:
    result.raise_for_expired()


async def _closing_movements(engine: AsyncEngine, reservation_id: UUID) -> list[tuple[str, int]]:
    async with AsyncSession(engine) as session:
        rows = await session.execute(
            select(InventoryMovement.movement_type, InventoryMovement.quantity).where(
                InventoryMovement.reference_id == reservation_id,
                InventoryMovement.movement_type.in_(["commit", "release"]),
            )
        )
        return sorted((kind, quantity) for kind, quantity in rows)


async def _audits(engine: AsyncEngine, reservation_id: UUID, action: str) -> list[AuditLog]:
    async with AsyncSession(engine) as session:
        statement = select(AuditLog).where(
            AuditLog.entity_id == reservation_id, AuditLog.action == action
        )
        return list((await session.scalars(statement)).all())


def _after(audit: AuditLog) -> dict[str, Any]:
    return {field: change["after"] for field, change in audit.metadata_["diff"].items()}


async def _status(engine: AsyncEngine, reservation_id: UUID) -> str:
    async with AsyncSession(engine) as session:
        reservation = await session.get(InventoryReservation, reservation_id)
        assert reservation is not None
        return reservation.status


async def test_commit_consumes_the_held_stock(catalog: Catalog, db_engine: AsyncEngine) -> None:
    first, second = await _stocked(catalog, 5, 3)
    held = await _reserve(db_engine, [(first.id, 2), (second.id, 3)])

    result = await _commit(db_engine, held.reservation_id)

    assert result.outcome is CommitOutcome.COMMITTED
    result.raise_for_expired()  # no-op unless expired
    first_item, second_item = await _item(db_engine, first.id), await _item(db_engine, second.id)
    assert (first_item.total_quantity, first_item.reserved_quantity) == (3, 0)
    assert (second_item.total_quantity, second_item.reserved_quantity) == (0, 0)
    assert await _status(db_engine, held.reservation_id) == "committed"
    assert await _closing_movements(db_engine, held.reservation_id) == [
        ("commit", 2),
        ("commit", 3),
    ]
    [audit] = await _audits(db_engine, held.reservation_id, "reservation.committed")
    assert _after(audit) == {"status": "committed"}
    await _assert_invariant(db_engine, [first.id, second.id])


async def test_commit_again_changes_nothing(catalog: Catalog, db_engine: AsyncEngine) -> None:
    [variant] = await _stocked(catalog, 5)
    held = await _reserve(db_engine, [(variant.id, 2)])
    await _commit(db_engine, held.reservation_id)

    again = await _commit(db_engine, held.reservation_id, now=utc_now() + PAST)

    assert again.outcome is CommitOutcome.ALREADY_COMMITTED
    assert (await _item(db_engine, variant.id)).total_quantity == 3
    assert await _closing_movements(db_engine, held.reservation_id) == [("commit", 2)]
    assert len(await _audits(db_engine, held.reservation_id, "reservation.committed")) == 1


async def test_expired_commit_frees_the_stock_and_is_409(
    catalog: Catalog, db_engine: AsyncEngine
) -> None:
    [variant] = await _stocked(catalog, 4)
    held = await _reserve(db_engine, [(variant.id, 3)])

    # At expires_at the reservation is already inactive: [created, expires_at).
    result = await _commit(db_engine, held.reservation_id, now=held.expires_at)

    assert result.outcome is CommitOutcome.EXPIRED
    await _error(_raise_for(result), 409, "RESERVATION_EXPIRED")
    item = await _item(db_engine, variant.id)
    assert (item.total_quantity, item.reserved_quantity) == (4, 0)
    assert await _status(db_engine, held.reservation_id) == "expired"
    assert await _closing_movements(db_engine, held.reservation_id) == [("release", 3)]
    [audit] = await _audits(db_engine, held.reservation_id, "reservation.expired")
    assert audit.metadata_["actor"] == "system"
    assert _after(audit) == {"status": "expired"}
    await _assert_invariant(db_engine, [variant.id])


async def test_expired_commit_rolled_back_by_the_caller_holds_nothing(
    catalog: Catalog, db_engine: AsyncEngine
) -> None:
    [variant] = await _stocked(catalog, 2)
    held = await _reserve(db_engine, [(variant.id, 2)])
    later = held.expires_at + timedelta(seconds=1)

    async with AsyncSession(db_engine) as session:
        await session.begin()
        result = await ReservationService(session).commit(held.reservation_id, now=later)
        assert result.outcome is CommitOutcome.EXPIRED
        await session.rollback()

    # The release was lost, but an expired reservation holds nothing anyway (ADR-036).
    assert await _status(db_engine, held.reservation_id) == "active"
    again = await _reserve(db_engine, [(variant.id, 2)], now=later)
    assert again.created
    await _assert_invariant(db_engine, [variant.id])


async def test_commit_after_a_partial_lazy_release_is_expired(
    catalog: Catalog, db_engine: AsyncEngine
) -> None:
    first, second = await _stocked(catalog, 1, 1)
    now = utc_now()
    old = await _reserve(db_engine, [(first.id, 1), (second.id, 1)], now=now - PAST)
    # Another order frees the first item of the old reservation lazily.
    await _reserve(db_engine, [(first.id, 1)], now=now)

    # Even with a ``now`` inside the old window, a partly released reservation is expired.
    result = await _commit(db_engine, old.reservation_id, now=now - PAST)

    assert result.outcome is CommitOutcome.EXPIRED
    assert await _closing_movements(db_engine, old.reservation_id) == [
        ("release", 1),
        ("release", 1),
    ]
    assert (await _item(db_engine, first.id)).total_quantity == 1
    assert (await _item(db_engine, second.id)).reserved_quantity == 0
    await _assert_invariant(db_engine, [first.id, second.id])


async def test_commit_of_a_released_reservation_is_expired(
    catalog: Catalog, db_engine: AsyncEngine
) -> None:
    [variant] = await _stocked(catalog, 2)
    held = await _reserve(db_engine, [(variant.id, 1)])
    await _release(db_engine, held.reservation_id)

    result = await _commit(db_engine, held.reservation_id)

    assert result.outcome is CommitOutcome.EXPIRED
    assert (await _item(db_engine, variant.id)).total_quantity == 2
    assert await _closing_movements(db_engine, held.reservation_id) == [("release", 1)]


async def test_release_returns_the_stock(catalog: Catalog, db_engine: AsyncEngine) -> None:
    [variant] = await _stocked(catalog, 3)
    held = await _reserve(db_engine, [(variant.id, 3)])

    result = await _release(db_engine, held.reservation_id, reason="  payment_failed ")
    again = await _release(db_engine, held.reservation_id)

    assert (result.outcome, again.outcome) == (
        ReleaseOutcome.RELEASED,
        ReleaseOutcome.ALREADY_CLOSED,
    )
    item = await _item(db_engine, variant.id)
    assert (item.total_quantity, item.reserved_quantity) == (3, 0)
    assert await _status(db_engine, held.reservation_id) == "released"
    async with AsyncSession(db_engine) as session:
        [movement] = (
            await session.scalars(
                select(InventoryMovement).where(
                    InventoryMovement.reference_id == held.reservation_id,
                    InventoryMovement.movement_type == "release",
                )
            )
        ).all()
    assert movement.reason == "payment_failed"
    [audit] = await _audits(db_engine, held.reservation_id, "reservation.released")
    assert _after(audit) == {"status": "released", "reason": "payment_failed", "expired": False}
    await _assert_invariant(db_engine, [variant.id])


async def test_release_of_an_expired_partly_released_reservation(
    catalog: Catalog, db_engine: AsyncEngine
) -> None:
    first, second = await _stocked(catalog, 1, 1)
    now = utc_now()
    old = await _reserve(db_engine, [(first.id, 1), (second.id, 1)], now=now - PAST)
    await _reserve(db_engine, [(first.id, 1)], now=now)

    result = await _release(db_engine, old.reservation_id, reason="order_cancelled", now=now)

    assert result.outcome is ReleaseOutcome.RELEASED
    async with AsyncSession(db_engine) as session:
        reasons = sorted(
            reason
            for reason in await session.scalars(
                select(InventoryMovement.reason).where(
                    InventoryMovement.reference_id == old.reservation_id,
                    InventoryMovement.movement_type == "release",
                )
            )
            if reason is not None
        )
    # One release per item: the lazy one (expired) and the caller's for the rest.
    assert reasons == ["expired", "order_cancelled"]
    [audit] = await _audits(db_engine, old.reservation_id, "reservation.released")
    assert _after(audit)["expired"] is True
    await _assert_invariant(db_engine, [first.id, second.id])


async def test_committed_reservation_cannot_be_released(
    catalog: Catalog, db_engine: AsyncEngine
) -> None:
    [variant] = await _stocked(catalog, 2)
    held = await _reserve(db_engine, [(variant.id, 1)])
    await _commit(db_engine, held.reservation_id)

    await _error(_release(db_engine, held.reservation_id), 409, "RESERVATION_ALREADY_CONSUMED")

    assert (await _item(db_engine, variant.id)).total_quantity == 1
    await _assert_invariant(db_engine, [variant.id])


@pytest.mark.parametrize("reason", ["", "   ", "x" * 501, None, 5])
async def test_release_needs_a_reason(
    catalog: Catalog, db_engine: AsyncEngine, reason: Any
) -> None:
    [variant] = await _stocked(catalog, 1)
    held = await _reserve(db_engine, [(variant.id, 1)])

    await _error(_release(db_engine, held.reservation_id, reason=reason), 400, "VALIDATION_ERROR")

    assert (await _item(db_engine, variant.id)).reserved_quantity == 1


async def test_unknown_reservation_is_404(db_engine: AsyncEngine) -> None:
    await _error(_commit(db_engine, uuid4()), 404, "NOT_FOUND")
    await _error(_release(db_engine, uuid4()), 404, "NOT_FOUND")


async def test_commit_and_release_need_the_callers_transaction(db_engine: AsyncEngine) -> None:
    async with AsyncSession(db_engine) as session:
        service = ReservationService(session)
        with pytest.raises(RuntimeError):
            await service.commit(uuid4())
        with pytest.raises(RuntimeError):
            await service.release(uuid4(), reason="x")


# --- commit and release under concurrency ----------------------------------------------


async def test_commit_racing_release_has_one_effect(
    catalog: Catalog, db_engine: AsyncEngine
) -> None:
    for _ in range(3):
        [variant] = await _stocked(catalog, 2)
        held = await _reserve(db_engine, [(variant.id, 2)])

        committed, released = await asyncio.gather(
            _commit(db_engine, held.reservation_id),
            _release(db_engine, held.reservation_id),
            return_exceptions=True,
        )

        item = await _item(db_engine, variant.id)
        assert isinstance(committed, CommitResult)
        if committed.outcome is CommitOutcome.COMMITTED:
            assert isinstance(released, AppError)
            assert released.code == "RESERVATION_ALREADY_CONSUMED"
            assert (item.total_quantity, item.reserved_quantity) == (0, 0)
        else:
            assert committed.outcome is CommitOutcome.EXPIRED
            assert isinstance(released, ReleaseResult)
            assert (item.total_quantity, item.reserved_quantity) == (2, 0)
        assert len(await _closing_movements(db_engine, held.reservation_id)) == 1
        await _assert_invariant(db_engine, [variant.id])


async def test_concurrent_commits_consume_once(catalog: Catalog, db_engine: AsyncEngine) -> None:
    [variant] = await _stocked(catalog, 3)
    held = await _reserve(db_engine, [(variant.id, 2)])

    results = await asyncio.gather(*(_commit(db_engine, held.reservation_id) for _ in range(4)))

    outcomes = sorted(result.outcome.value for result in results)
    assert outcomes == ["already_committed"] * 3 + ["committed"]
    assert (await _item(db_engine, variant.id)).total_quantity == 1
    assert await _closing_movements(db_engine, held.reservation_id) == [("commit", 2)]
    await _assert_invariant(db_engine, [variant.id])


async def test_expired_commit_racing_another_orders_reserve_releases_once(
    catalog: Catalog, db_engine: AsyncEngine
) -> None:
    [variant] = await _stocked(catalog, 1)
    now = utc_now()
    old = await _reserve(db_engine, [(variant.id, 1)], now=now - PAST)

    committed, reserved = await asyncio.gather(
        _commit(db_engine, old.reservation_id, now=now),
        _reserve(db_engine, [(variant.id, 1)], now=now),
    )

    assert committed.outcome is CommitOutcome.EXPIRED and reserved.created
    assert await _closing_movements(db_engine, old.reservation_id) == [("release", 1)]
    item = await _item(db_engine, variant.id)
    assert (item.total_quantity, item.reserved_quantity) == (1, 1)
    await _assert_invariant(db_engine, [variant.id])


async def test_re_reserve_racing_commit_of_the_same_order(
    catalog: Catalog, db_engine: AsyncEngine
) -> None:
    for _ in range(3):
        [variant] = await _stocked(catalog, 2)
        order_id = uuid4()
        held = await _reserve(db_engine, [(variant.id, 1)], order_id=order_id)
        # The re-reserve sees the old reservation as expired; the commit does not.
        later = held.expires_at + timedelta(seconds=1)

        committed, renewed = await asyncio.gather(
            _commit(db_engine, held.reservation_id, now=utc_now()),
            _reserve(db_engine, [(variant.id, 1)], order_id=order_id, now=later),
            return_exceptions=True,
        )

        assert isinstance(committed, CommitResult)
        if committed.outcome is CommitOutcome.COMMITTED:
            # Never an IntegrityError: the order is consumed, so no second reservation.
            assert isinstance(renewed, AppError)
            assert renewed.code == "RESERVATION_ALREADY_CONSUMED"
            assert (await _item(db_engine, variant.id)).total_quantity == 1
        else:
            assert committed.outcome is CommitOutcome.EXPIRED
            assert isinstance(renewed, ReservationResult) and renewed.created
        await _assert_invariant(db_engine, [variant.id])


async def test_multi_variant_commit_and_crossing_reserves_do_not_deadlock(
    catalog: Catalog, db_engine: AsyncEngine
) -> None:
    first, second = await _stocked(catalog, 10, 10)
    held = await _reserve(db_engine, [(first.id, 2), (second.id, 2)])

    committed, *reserved = await asyncio.gather(
        _commit(db_engine, held.reservation_id),
        *(
            _reserve(db_engine, [(second.id, 1), (first.id, 1)] if index % 2 else [(first.id, 1)])
            for index in range(6)
        ),
    )

    assert isinstance(committed, CommitResult) and committed.outcome is CommitOutcome.COMMITTED
    assert len(reserved) == 6
    assert (await _item(db_engine, first.id)).total_quantity == 8
    await _assert_invariant(db_engine, [first.id, second.id])


async def test_commit_racing_a_manual_decrease(catalog: Catalog, db_engine: AsyncEngine) -> None:
    [variant] = await _stocked(catalog, 3)
    held = await _reserve(db_engine, [(variant.id, 2)])

    async def decrease() -> object:
        async with AsyncSession(db_engine) as session:
            return await InventoryService(session, InventoryRepository(session)).adjust(
                actor_id=None,
                variant_id=variant.id,
                kind=AdjustmentType.DECREASE,
                quantity=1,
                reason="damaged",
            )

    committed, _ = await asyncio.gather(_commit(db_engine, held.reservation_id), decrease())

    assert committed.outcome is CommitOutcome.COMMITTED
    item = await _item(db_engine, variant.id)
    assert (item.total_quantity, item.reserved_quantity) == (0, 0)
    await _assert_invariant(db_engine, [variant.id])
