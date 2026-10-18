"""Cleanup job for expired reservations (INV-06, ADR-036).

Each worker database keeps other tests' leftovers, so every assertion is about this test's
own reservations, never about the sweep's totals.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from conftest import Catalog
from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from test_reservations import (
    PAST,
    _assert_invariant,
    _audits,
    _closing_movements,
    _commit,
    _item,
    _release,
    _reserve,
    _status,
    _stocked,
)

from app.core.config import Settings
from app.core.time import utc_now
from app.db.models import InventoryItem, InventoryReservation
from app.main import create_app
from app.modules.inventory.jobs import (
    JOB_LOCK_KEY,
    JOB_LOCK_NAMESPACE,
    SweepResult,
    run_sweeper,
    sweep_expired_reservations,
)
from app.modules.inventory.reservation import (
    CommitOutcome,
    ReleaseResult,
    ReservationService,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("order_factory")]


async def _wait_for_lock_waiter(engine: AsyncEngine) -> None:
    """Until a backend in this database waits on a lock (bounded polling, no fixed sleep)."""
    async with AsyncSession(engine) as session:
        for _ in range(500):
            waiting = await session.scalar(
                select(func.count())
                .select_from(text("pg_locks"))
                # Only this worker's database: other xdist workers share the server.
                .where(
                    text(
                        # Row-lock waits are on transaction ids (database NULL); the
                        # waiting backend tells which database it belongs to.
                        "NOT granted AND pid IN (SELECT pid FROM pg_stat_activity"
                        " WHERE datname = current_database())"
                    )
                )
            )
            if waiting:
                return
            await asyncio.sleep(0.01)
    raise AssertionError("no transaction started waiting for the lock")


async def test_sweep_closes_expired_and_keeps_live_reservations(
    catalog: Catalog, db_engine: AsyncEngine
) -> None:
    first, second = await _stocked(catalog, 3, 3)
    now = utc_now()
    old = await _reserve(db_engine, [(first.id, 2), (second.id, 1)], now=now - PAST)
    live = await _reserve(db_engine, [(second.id, 2)], now=now)

    result = await sweep_expired_reservations(db_engine, now=now)

    assert result.ran
    assert await _status(db_engine, old.reservation_id) == "expired"
    assert await _status(db_engine, live.reservation_id) == "active"
    assert await _closing_movements(db_engine, old.reservation_id) == [
        ("release", 1),
        ("release", 2),
    ]
    assert (await _item(db_engine, first.id)).reserved_quantity == 0
    assert (await _item(db_engine, second.id)).reserved_quantity == 2
    [audit] = await _audits(db_engine, old.reservation_id, "reservation.expired")
    assert audit.metadata_["actor"] == "system"
    await _assert_invariant(db_engine, [first.id, second.id])


async def test_sweep_closes_a_partly_released_reservation(
    catalog: Catalog, db_engine: AsyncEngine
) -> None:
    first, second = await _stocked(catalog, 1, 1)
    now = utc_now()
    old = await _reserve(db_engine, [(first.id, 1), (second.id, 1)], now=now - PAST)
    await _reserve(db_engine, [(first.id, 1)], now=now)  # frees the first item lazily

    await sweep_expired_reservations(db_engine, now=now)

    assert await _status(db_engine, old.reservation_id) == "expired"
    # One release per item: the lazy one and the job's; never a second for the first item.
    assert await _closing_movements(db_engine, old.reservation_id) == [
        ("release", 1),
        ("release", 1),
    ]
    await _assert_invariant(db_engine, [first.id, second.id])


async def test_sweep_pages_through_small_batches(catalog: Catalog, db_engine: AsyncEngine) -> None:
    [variant] = await _stocked(catalog, 5)
    now = utc_now()
    old = [
        await _reserve(db_engine, [(variant.id, 1)], now=now - PAST - timedelta(seconds=index))
        for index in range(5)
    ]

    await sweep_expired_reservations(db_engine, now=now, batch_size=2)

    assert [await _status(db_engine, held.reservation_id) for held in old] == ["expired"] * 5
    assert (await _item(db_engine, variant.id)).reserved_quantity == 0
    await _assert_invariant(db_engine, [variant.id])


async def test_sweep_skips_a_reservation_row_held_by_another_transaction(
    catalog: Catalog, db_engine: AsyncEngine
) -> None:
    [variant] = await _stocked(catalog, 1)
    now = utc_now()
    old = await _reserve(db_engine, [(variant.id, 1)], now=now - PAST)

    async with AsyncSession(db_engine) as holder, holder.begin():
        await holder.execute(
            select(InventoryReservation.id)
            .where(InventoryReservation.id == old.reservation_id)
            .with_for_update()
        )
        result = await sweep_expired_reservations(db_engine, now=now)
        assert result.ran and result.skipped >= 1
        assert await _status(db_engine, old.reservation_id) == "active"

    await sweep_expired_reservations(db_engine, now=now)
    assert await _status(db_engine, old.reservation_id) == "expired"
    await _assert_invariant(db_engine, [variant.id])


async def test_sweep_skips_after_lock_timeout_on_a_held_item(
    catalog: Catalog, db_engine: AsyncEngine
) -> None:
    [variant] = await _stocked(catalog, 1)
    now = utc_now()
    old = await _reserve(db_engine, [(variant.id, 1)], now=now - PAST)

    async with AsyncSession(db_engine) as holder, holder.begin():
        await holder.execute(
            select(InventoryItem.id).where(InventoryItem.variant_id == variant.id).with_for_update()
        )
        result = await sweep_expired_reservations(db_engine, now=now, lock_timeout_ms=50)
        assert result.ran and result.failed == 0
        assert await _status(db_engine, old.reservation_id) == "active"

    await sweep_expired_reservations(db_engine, now=now)
    assert await _status(db_engine, old.reservation_id) == "expired"


async def test_sweep_skips_the_round_when_another_runner_holds_the_job_lock(
    db_engine: AsyncEngine,
) -> None:
    async with db_engine.connect() as other, other.begin():
        await other.execute(select(func.pg_advisory_xact_lock(JOB_LOCK_NAMESPACE, JOB_LOCK_KEY)))
        assert await sweep_expired_reservations(db_engine) == SweepResult(ran=False)

    assert (await sweep_expired_reservations(db_engine)).ran


async def test_cancelled_sweep_does_not_keep_the_job_lock(
    catalog: Catalog, db_engine: AsyncEngine
) -> None:
    [variant] = await _stocked(catalog, 1)
    now = utc_now()
    old = await _reserve(db_engine, [(variant.id, 1)], now=now - PAST)

    async with AsyncSession(db_engine) as holder, holder.begin():
        await holder.execute(
            select(InventoryItem.id).where(InventoryItem.variant_id == variant.id).with_for_update()
        )
        # The sweep blocks on the item lock while it holds the job lock; cancel it there.
        sweep = asyncio.create_task(
            sweep_expired_reservations(db_engine, now=now, lock_timeout_ms=60_000)
        )
        await _wait_for_lock_waiter(db_engine)
        sweep.cancel()
        with pytest.raises(asyncio.CancelledError):
            await sweep

    assert (await sweep_expired_reservations(db_engine, now=now)).ran
    assert await _status(db_engine, old.reservation_id) == "expired"
    await _assert_invariant(db_engine, [variant.id])


async def test_concurrent_sweeps_close_each_reservation_once(
    catalog: Catalog, db_engine: AsyncEngine
) -> None:
    [variant] = await _stocked(catalog, 4)
    now = utc_now()
    old = [await _reserve(db_engine, [(variant.id, 1)], now=now - PAST) for _ in range(4)]

    results = await asyncio.gather(
        *(sweep_expired_reservations(db_engine, now=now) for _ in range(3))
    )

    assert any(result.ran for result in results)
    for held in old:
        assert await _status(db_engine, held.reservation_id) == "expired"
        assert len(await _audits(db_engine, held.reservation_id, "reservation.expired")) == 1
        assert await _closing_movements(db_engine, held.reservation_id) == [("release", 1)]
    await _assert_invariant(db_engine, [variant.id])


async def test_concurrent_expire_calls_release_once(
    catalog: Catalog, db_engine: AsyncEngine
) -> None:
    [variant] = await _stocked(catalog, 2)
    now = utc_now()
    old = await _reserve(db_engine, [(variant.id, 2)], now=now - PAST)

    async def expire() -> bool:
        async with AsyncSession(db_engine) as session, session.begin():
            return await ReservationService(session).expire(old.reservation_id, now=now)

    results = await asyncio.gather(*(expire() for _ in range(4)))

    assert sorted(results) == [False, False, False, True]
    assert await _closing_movements(db_engine, old.reservation_id) == [("release", 2)]
    await _assert_invariant(db_engine, [variant.id])


async def test_expire_skips_live_closed_and_unknown_reservations(
    catalog: Catalog, db_engine: AsyncEngine
) -> None:
    [variant] = await _stocked(catalog, 3)
    live = await _reserve(db_engine, [(variant.id, 1)])
    committed = await _reserve(db_engine, [(variant.id, 1)])
    await _commit(db_engine, committed.reservation_id)

    async with AsyncSession(db_engine) as session, session.begin():
        service = ReservationService(session)
        assert not await service.expire(live.reservation_id)
        assert not await service.expire(committed.reservation_id, now=utc_now() + PAST)
        assert not await service.expire(UUID(int=0))
    assert await _status(db_engine, live.reservation_id) == "active"
    assert await _status(db_engine, committed.reservation_id) == "committed"


async def test_commit_racing_the_job_never_does_both(
    catalog: Catalog, db_engine: AsyncEngine
) -> None:
    for _ in range(3):
        [variant] = await _stocked(catalog, 2)
        held = await _reserve(db_engine, [(variant.id, 2)])
        # Valid for the commit, expired for the job.
        job_now = held.expires_at + timedelta(seconds=1)

        committed, _ = await asyncio.gather(
            _commit(db_engine, held.reservation_id, now=utc_now()),
            sweep_expired_reservations(db_engine, now=job_now),
        )

        status = await _status(db_engine, held.reservation_id)
        item = await _item(db_engine, variant.id)
        if committed.outcome is CommitOutcome.COMMITTED:
            assert status == "committed" and item.total_quantity == 0
            assert await _closing_movements(db_engine, held.reservation_id) == [("commit", 2)]
        else:
            assert committed.outcome is CommitOutcome.EXPIRED
            assert status == "expired" and item.total_quantity == 2
            assert await _closing_movements(db_engine, held.reservation_id) == [("release", 2)]
        await _assert_invariant(db_engine, [variant.id])


async def test_release_racing_the_job_releases_once(
    catalog: Catalog, db_engine: AsyncEngine
) -> None:
    for _ in range(3):
        [variant] = await _stocked(catalog, 2)
        now = utc_now()
        old = await _reserve(db_engine, [(variant.id, 2)], now=now - PAST)

        released, _ = await asyncio.gather(
            _release(db_engine, old.reservation_id, now=now),
            sweep_expired_reservations(db_engine, now=now),
        )

        assert isinstance(released, ReleaseResult)
        assert await _status(db_engine, old.reservation_id) in {"released", "expired"}
        assert await _closing_movements(db_engine, old.reservation_id) == [("release", 2)]
        assert (await _item(db_engine, variant.id)).reserved_quantity == 0
        await _assert_invariant(db_engine, [variant.id])


# --- the loop in the application lifespan ------------------------------------------------


async def test_sweeper_survives_a_failed_round() -> None:
    calls: list[int] = []
    done = asyncio.Event()

    async def sweep(engine: Any) -> SweepResult:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("database away")
        if len(calls) == 3:
            done.set()
        return SweepResult(ran=True)

    task = asyncio.create_task(run_sweeper(engine=None, interval_seconds=0, sweep=sweep))  # type: ignore[arg-type]
    await asyncio.wait_for(done.wait(), timeout=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(calls) >= 3


async def test_lifespan_starts_and_stops_the_sweeper(settings: Settings) -> None:
    application = create_app(settings.model_copy(update={"reservation_sweep_seconds": 60}))
    async with application.router.lifespan_context(application):
        sweeper = application.state.reservation_sweeper
        assert isinstance(sweeper, asyncio.Task) and not sweeper.done()
    assert sweeper.cancelled()


async def test_sweeper_is_off_at_zero(settings: Settings) -> None:
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        assert application.state.reservation_sweeper is None


@pytest.mark.parametrize("value", [-1, 3601])
def test_sweep_interval_is_bounded(settings: Settings, value: int) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(settings.model_dump() | {"reservation_sweep_seconds": value})


@pytest.mark.parametrize(("batch_size", "max_batches"), [(0, 1), (1, 0)])
async def test_sweep_limits_must_be_positive(
    db_engine: AsyncEngine, batch_size: int, max_batches: int
) -> None:
    with pytest.raises(ValueError):
        await sweep_expired_reservations(db_engine, batch_size=batch_size, max_batches=max_batches)
