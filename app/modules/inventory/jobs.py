"""Cleanup of expired reservations (INV-06, ADR-036) and of the orders they held (ORD-06).

An expired reservation already holds nothing for every check, so this job only brings the
counters and statuses in line: it releases what expired reservations still hold and closes
them as ``expired``. Nothing depends on it running on time.

- One runner at a time: a transaction-level advisory lock on a dedicated connection, held
  for the whole sweep and released with that transaction (it cannot leak into the pool).
  Other instances skip the round.
- Each reservation is closed in its own transaction (ADR-036), locking its items and then
  its row with ``SKIP LOCKED``: a reservation a commit or release is deciding is skipped.
- Keyset paging on ``(expires_at, id)`` with a batch cap, so skipped rows cannot loop.
- A reservation of an order also cancels that order (D34, ADR-050), in the same
  transaction and in the ADR-048 lock order: the order advisory lock (try) → the order row
  (``SKIP LOCKED``) → items → reservation row → redemption. A busy order is skipped and
  retried next round. A second pass cancels ``pending_payment`` orders whose reservation
  was already closed without a commit (by an older job, e.g. during a rolling deploy).

Run once by hand: ``python -m app.modules.inventory.jobs``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Final
from uuid import UUID

from sqlalchemy import Exists, func, select, text, tuple_
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.time import utc_now
from app.db.models import InventoryReservation, Order, OrderStatus, ReservationStatus
from app.modules.inventory.reservation import ReservationService
from app.modules.orders.cancel import OrderCancellation, lock_order, order_advisory_lock

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
    # Locked by a commit, release or cancel, or no longer active/expired when locked.
    skipped: int = 0
    failed: int = 0
    # Orders cancelled because their reservation expired (D34).
    cancelled: int = 0


class _Outcome(Enum):
    SKIPPED = "skipped"
    EXPIRED = "expired"
    # Expired, and its order cancelled in the same transaction.
    CANCELLED = "cancelled"


class _Skip(Exception):
    """Leave this one for the next round (its transaction rolls back)."""


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
        counts = {outcome: 0 for outcome in _Outcome}
        failed = 0
        cursor: tuple[datetime, UUID] | None = None
        for _ in range(max_batches):
            batch = await _expired_batch(engine, cutoff, cursor, batch_size)
            for reservation_id, expires_at, order_id in batch:
                cursor = (expires_at, reservation_id)
                outcome = await _expire_one(engine, reservation_id, order_id, now, lock_timeout_ms)
                if outcome is None:
                    failed += 1
                else:
                    counts[outcome] += 1
            if len(batch) < batch_size:
                break
        orphans_cancelled = 0
        order_cursor: UUID | None = None
        for _ in range(max_batches):
            orphans = await _orphaned_orders(engine, order_cursor, batch_size)
            for order_id in orphans:
                order_cursor = order_id
                outcome = await _cancel_orphan(engine, order_id, lock_timeout_ms)
                if outcome is None:
                    failed += 1
                elif outcome is _Outcome.SKIPPED:
                    counts[outcome] += 1
                else:
                    orphans_cancelled += 1
            if len(orphans) < batch_size:
                break
    result = SweepResult(
        ran=True,
        expired=counts[_Outcome.EXPIRED] + counts[_Outcome.CANCELLED],
        skipped=counts[_Outcome.SKIPPED],
        failed=failed,
        cancelled=counts[_Outcome.CANCELLED] + orphans_cancelled,
    )
    if result.expired or result.skipped or failed or result.cancelled:
        logger.info(
            "reservation.sweep",
            extra={
                "expired": result.expired,
                "skipped": result.skipped,
                "failed": failed,
                "cancelled": result.cancelled,
            },
        )
    return result


async def _expired_batch(
    engine: AsyncEngine,
    cutoff: datetime,
    cursor: tuple[datetime, UUID] | None,
    batch_size: int,
) -> list[tuple[UUID, datetime, UUID | None]]:
    statement = select(
        InventoryReservation.id, InventoryReservation.expires_at, InventoryReservation.order_id
    ).where(
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
        return [
            (reservation_id, expires_at, order_id) for reservation_id, expires_at, order_id in rows
        ]


async def _orphaned_orders(engine: AsyncEngine, cursor: UUID | None, batch_size: int) -> list[UUID]:
    """``pending_payment`` orders whose reservation was closed without a commit."""

    def reservation_of_order(*statuses: ReservationStatus) -> Exists:
        return (
            select(InventoryReservation.id)
            .where(
                InventoryReservation.order_id == Order.id,
                InventoryReservation.status.in_(statuses),
            )
            .exists()
        )

    statement = select(Order.id).where(
        Order.status == OrderStatus.PENDING_PAYMENT,
        reservation_of_order(ReservationStatus.EXPIRED, ReservationStatus.RELEASED),
        ~reservation_of_order(ReservationStatus.ACTIVE, ReservationStatus.COMMITTED),
    )
    if cursor is not None:
        statement = statement.where(Order.id > cursor)
    statement = statement.order_by(Order.id).limit(batch_size)
    async with AsyncSession(engine) as session:
        return list((await session.scalars(statement)).all())


async def _lock_order_or_skip(session: AsyncSession, order_id: UUID) -> Order:
    """The order's advisory lock and row, or ``_Skip``: the job never waits on an order."""
    if not await session.scalar(order_advisory_lock(order_id, wait=False)):
        raise _Skip
    order = await lock_order(session, order_id, skip_locked=True)
    if order is None:
        raise _Skip
    return order


async def _expire_one(
    engine: AsyncEngine,
    reservation_id: UUID,
    order_id: UUID | None,
    now: datetime | None,
    lock_timeout_ms: int,
) -> _Outcome | None:
    """What happened to one reservation; None if it failed (logged; the sweep goes on)."""
    try:
        async with AsyncSession(engine) as session, session.begin():
            # A stuck writer on one item must not stall the sweep (it holds the job lock).
            await session.execute(text(f"SET LOCAL lock_timeout = {int(lock_timeout_ms)}"))
            # ``order_id`` never changes, so reading it before the locks is safe.
            order = None if order_id is None else await _lock_order_or_skip(session, order_id)
            if not await ReservationService(session).expire(reservation_id, now=now):
                raise _Skip
            if order is None:
                return _Outcome.EXPIRED
            if order.status != OrderStatus.PENDING_PAYMENT:
                logger.warning(
                    "reservation.expired_for_settled_order",
                    extra={"order_id": str(order.id), "order_status": order.status},
                )
                return _Outcome.EXPIRED
            await OrderCancellation(session).cancel_locked(order, actor_user_id=None)
            return _Outcome.CANCELLED
    except _Skip:
        return _Outcome.SKIPPED
    except DBAPIError as error:
        if getattr(error.orig, "sqlstate", None) == LOCK_NOT_AVAILABLE:
            return _Outcome.SKIPPED
        logger.exception("reservation.sweep_failed", extra={"reservation_id": str(reservation_id)})
        return None
    except Exception:
        logger.exception("reservation.sweep_failed", extra={"reservation_id": str(reservation_id)})
        return None


async def _cancel_orphan(
    engine: AsyncEngine, order_id: UUID, lock_timeout_ms: int
) -> _Outcome | None:
    """Cancel a pending order left without a live reservation; None if it failed."""
    try:
        async with AsyncSession(engine) as session, session.begin():
            await session.execute(text(f"SET LOCAL lock_timeout = {int(lock_timeout_ms)}"))
            order = await _lock_order_or_skip(session, order_id)
            if order.status != OrderStatus.PENDING_PAYMENT:
                raise _Skip
            await OrderCancellation(session).cancel_locked(
                order, actor_user_id=None, force_expired=True
            )
            return _Outcome.CANCELLED
    except _Skip:
        return _Outcome.SKIPPED
    except DBAPIError as error:
        if getattr(error.orig, "sqlstate", None) == LOCK_NOT_AVAILABLE:
            return _Outcome.SKIPPED
        logger.exception("order.expiry_cancel_failed", extra={"order_id": str(order_id)})
        return None
    except Exception:
        logger.exception("order.expiry_cancel_failed", extra={"order_id": str(order_id)})
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
