"""Cleanup of expired reservations (INV-06, ADR-036).

An expired reservation already holds nothing for every check, so this job only brings the
counters and statuses in line: it releases what expired reservations still hold and closes
them as ``expired``. Nothing depends on it running on time.

- One runner at a time: a transaction-level advisory lock on a dedicated connection, held
  for the whole sweep and released with that transaction (it cannot leak into the pool).
  Other instances skip the round.
- Each reservation is closed in its own transaction (ADR-036), locking its items and then
  its row with ``SKIP LOCKED``: a reservation a commit or release is deciding is skipped.
- Keyset paging on ``(expires_at, id)`` with a batch cap, so skipped rows cannot loop.

Run once by hand: ``python -m app.modules.inventory.jobs``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Final
from uuid import UUID

from sqlalchemy import func, select, text, tuple_
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.time import utc_now
from app.db.models import InventoryReservation, ReservationStatus
from app.modules.inventory.reservation import ReservationService

logger = logging.getLogger(__name__)

# Advisory lock of the job; reserve's per-order locks use ORDER_LOCK_NAMESPACE (73_011).
JOB_LOCK_NAMESPACE: Final = 73_012
JOB_LOCK_KEY: Final = 1
SWEEP_BATCH_SIZE: Final = 100
SWEEP_MAX_BATCHES: Final = 50
# Longest wait for one reservation's item locks before it is skipped this round.
SWEEP_LOCK_TIMEOUT_MS: Final = 2000
LOCK_NOT_AVAILABLE: Final = "55P03"  # PostgreSQL lock_not_available


@dataclass(frozen=True, slots=True)
class SweepResult:
    # False when another runner held the job lock and this round was skipped.
    ran: bool
    expired: int = 0
    # Locked by a commit or release, or no longer active/expired when locked.
    skipped: int = 0
    failed: int = 0


async def sweep_expired_reservations(
    engine: AsyncEngine,
    *,
    now: datetime | None = None,
    batch_size: int = SWEEP_BATCH_SIZE,
    max_batches: int = SWEEP_MAX_BATCHES,
    lock_timeout_ms: int = SWEEP_LOCK_TIMEOUT_MS,
) -> SweepResult:
    """Close reservations expired at ``now`` (default: the time of the sweep)."""
    if batch_size < 1 or max_batches < 1:
        raise ValueError("batch_size and max_batches must be at least 1")
    async with engine.connect() as guard, guard.begin():
        # The guard idles in its transaction for the whole sweep; a server-side idle
        # timeout must not end it (and the job lock with it) halfway.
        await guard.execute(text("SET LOCAL idle_in_transaction_session_timeout = 0"))
        acquired = await guard.scalar(
            select(func.pg_try_advisory_xact_lock(JOB_LOCK_NAMESPACE, JOB_LOCK_KEY))
        )
        if not acquired:
            return SweepResult(ran=False)
        cutoff = now or utc_now()
        expired = skipped = failed = 0
        cursor: tuple[datetime, UUID] | None = None
        for _ in range(max_batches):
            batch = await _expired_batch(engine, cutoff, cursor, batch_size)
            for reservation_id, expires_at in batch:
                cursor = (expires_at, reservation_id)
                outcome = await _expire_one(engine, reservation_id, now, lock_timeout_ms)
                if outcome is None:
                    failed += 1
                elif outcome:
                    expired += 1
                else:
                    skipped += 1
            if len(batch) < batch_size:
                break
    result = SweepResult(ran=True, expired=expired, skipped=skipped, failed=failed)
    if expired or skipped or failed:
        logger.info(
            "reservation.sweep",
            extra={"expired": expired, "skipped": skipped, "failed": failed},
        )
    return result


async def _expired_batch(
    engine: AsyncEngine,
    cutoff: datetime,
    cursor: tuple[datetime, UUID] | None,
    batch_size: int,
) -> list[tuple[UUID, datetime]]:
    statement = select(InventoryReservation.id, InventoryReservation.expires_at).where(
        InventoryReservation.status == ReservationStatus.ACTIVE,
        InventoryReservation.expires_at <= cutoff,
    )
    if cursor is not None:
        statement = statement.where(
            tuple_(InventoryReservation.expires_at, InventoryReservation.id) > tuple_(*cursor)
        )
    statement = statement.order_by(InventoryReservation.expires_at, InventoryReservation.id).limit(
        batch_size
    )
    async with AsyncSession(engine) as session:
        rows = await session.execute(statement)
        return [(reservation_id, expires_at) for reservation_id, expires_at in rows]


async def _expire_one(
    engine: AsyncEngine, reservation_id: UUID, now: datetime | None, lock_timeout_ms: int
) -> bool | None:
    """True if closed, False if skipped, None if it failed (logged; the sweep goes on)."""
    try:
        async with AsyncSession(engine) as session, session.begin():
            # A stuck writer on one item must not stall the sweep (it holds the job lock).
            await session.execute(text(f"SET LOCAL lock_timeout = {int(lock_timeout_ms)}"))
            return await ReservationService(session).expire(reservation_id, now=now)
    except DBAPIError as error:
        if getattr(error.orig, "sqlstate", None) == LOCK_NOT_AVAILABLE:
            return False
        logger.exception("reservation.sweep_failed", extra={"reservation_id": str(reservation_id)})
        return None
    except Exception:
        logger.exception("reservation.sweep_failed", extra={"reservation_id": str(reservation_id)})
        return None


Sweep = Callable[[AsyncEngine], Awaitable[SweepResult]]


async def run_sweeper(
    engine: AsyncEngine,
    interval_seconds: float,
    sweep: Sweep = sweep_expired_reservations,
) -> None:
    """Sweep every ``interval_seconds`` until cancelled; a failed round is logged, not fatal."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await sweep(engine)
        except Exception:
            logger.exception("reservation.sweep_round_failed")


async def _main() -> None:
    from app.core.config import get_settings
    from app.db.session import create_database_engine

    engine = create_database_engine(get_settings())
    try:
        result = await sweep_expired_reservations(engine)
        print(result)  # noqa: T201 - manual run reports to the console
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
