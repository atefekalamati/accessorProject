"""Reconciliation of pending payments (PAY-04, ADR-049, ADR-051).

A callback can be lost (the customer closed the tab, the gateway gave up). Every round
verifies the payments still ``pending`` after ``PAYMENT_PENDING_STALE_SECONDS`` with the
gateway and applies the result exactly as a callback would (``PaymentProcessor``):

- no gateway reference (the request never came back) → ``failed`` (``request_lost``)
- PAID / FAILED → applied (paid, refund_required or failed)
- still PENDING long after its gateway session ended → ``failed`` (``abandoned``)

One runner at a time (a transaction-level advisory lock on a dedicated connection, like
the reservation sweeper). Each payment is verified outside any transaction and applied in
its own one with try-locks and a ``lock_timeout``: a busy order, cart or item is skipped
and retried next round. The round also deletes payment events past their retention.

Run once by hand: ``python -m app.modules.payments.jobs``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final
from uuid import UUID

from sqlalchemy import delete, func, select, text, tuple_
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import Settings
from app.core.time import utc_now
from app.db.models import Payment, PaymentEvent, PaymentStatus
from app.modules.orders.cancel import lock_order, order_advisory_lock
from app.modules.payments.common import close_payment, lock_payment
from app.modules.payments.gateways.base import GatewayUnavailable, PaymentGateway, VerifyOutcome
from app.modules.payments.processing import BusyError, Outcome, PaymentProcessor
from app.modules.payments.service import call_gateway

logger = logging.getLogger(__name__)

# Advisory lock of this job; orders use 73_011 and the reservation sweeper 73_012.
JOB_LOCK_NAMESPACE: Final = 73_013
JOB_LOCK_KEY: Final = 1
RECONCILE_BATCH_SIZE: Final = 50
RECONCILE_MAX_BATCHES: Final = 20
RECONCILE_LOCK_TIMEOUT_MS: Final = 2000
EVENT_PURGE_BATCH: Final = 1000
LOCK_NOT_AVAILABLE: Final = "55P03"
# Consecutive unreachable verifies after which the round stops (each waits the timeout).
MAX_GATEWAY_DOWN: Final = 3
# Old events are trimmed at most this often (the scan is not worth every round).
EVENT_PURGE_INTERVAL_SECONDS: Final = 3600
_GATEWAY_DOWN: Final = "gateway_down"


@dataclass(frozen=True, slots=True)
class ReconcileResult:
    ran: bool
    # A verify result was applied (paid, failed or refund_required).
    applied: int = 0
    # Closed without a decisive verify (request_lost, abandoned).
    closed: int = 0
    # Still pending at the gateway, or a lock was busy: next round.
    unchanged: int = 0
    failed: int = 0
    purged_events: int = 0


async def reconcile_pending_payments(
    engine: AsyncEngine,
    gateway: PaymentGateway,
    settings: Settings,
    *,
    now: datetime | None = None,
    batch_size: int = RECONCILE_BATCH_SIZE,
    max_batches: int = RECONCILE_MAX_BATCHES,
    lock_timeout_ms: int = RECONCILE_LOCK_TIMEOUT_MS,
    purge: bool = True,
) -> ReconcileResult:
    """Verify and settle stale pending payments; ``purge`` also trims old events."""
    if batch_size < 1 or max_batches < 1:
        raise ValueError("batch_size and max_batches must be at least 1")
    async with engine.connect() as guard, guard.begin():
        await guard.execute(text("SET LOCAL idle_in_transaction_session_timeout = 0"))
        acquired = await guard.scalar(
            select(func.pg_try_advisory_xact_lock(JOB_LOCK_NAMESPACE, JOB_LOCK_KEY))
        )
        if not acquired:
            return ReconcileResult(ran=False)
        now = now or utc_now()
        stale = timedelta(seconds=settings.payment_pending_stale_seconds)
        counts = {"applied": 0, "closed": 0, "unchanged": 0, "failed": 0}
        cursor: tuple[datetime, UUID] | None = None
        down = 0
        for _ in range(max_batches):
            batch = await _stale_batch(engine, now - stale, cursor, batch_size)
            for payment_id, created_at in batch:
                cursor = (created_at, payment_id)
                kind = await _reconcile_one(
                    engine, gateway, settings, payment_id, now, stale, lock_timeout_ms
                )
                down = down + 1 if kind == _GATEWAY_DOWN else 0
                counts["failed" if kind == _GATEWAY_DOWN else kind] += 1
                if down >= MAX_GATEWAY_DOWN:
                    break
            if down >= MAX_GATEWAY_DOWN:
                # Each call would wait the full timeout: leave the rest for a later round.
                logger.warning("payment.reconcile_gateway_down", extra={"after": down})
                break
            if len(batch) < batch_size:
                break
        purged = 0
        if purge:
            purged = await _purge_events(
                engine, now - timedelta(days=settings.payment_event_retention_days)
            )
    result = ReconcileResult(ran=True, purged_events=purged, **counts)
    if any(counts.values()) or purged:
        logger.info("payment.reconcile", extra={**counts, "purged_events": purged})
    return result


async def _stale_batch(
    engine: AsyncEngine,
    cutoff: datetime,
    cursor: tuple[datetime, UUID] | None,
    batch_size: int,
) -> list[tuple[UUID, datetime]]:
    statement = select(Payment.id, Payment.created_at).where(
        Payment.status == PaymentStatus.PENDING, Payment.created_at <= cutoff
    )
    if cursor is not None:
        statement = statement.where(tuple_(Payment.created_at, Payment.id) > tuple_(*cursor))
    statement = statement.order_by(Payment.created_at, Payment.id).limit(batch_size)
    async with AsyncSession(engine) as session:
        return [
            (payment_id, created_at) for payment_id, created_at in await session.execute(statement)
        ]


async def _reconcile_one(
    engine: AsyncEngine,
    gateway: PaymentGateway,
    settings: Settings,
    payment_id: UUID,
    now: datetime,
    stale: timedelta,
    lock_timeout_ms: int,
) -> str:
    """``applied``, ``closed``, ``unchanged`` or ``failed`` (logged; the round goes on)."""
    try:
        async with AsyncSession(engine) as session:
            payment = await session.get(Payment, payment_id)
        if payment is None or payment.status != PaymentStatus.PENDING:
            return "unchanged"
        if payment.gateway_reference is None:
            return await _close(engine, payment_id, "request_lost", lock_timeout_ms)
        try:
            result = await call_gateway(
                gateway.verify(reference=payment.gateway_reference, amount=payment.amount),
                settings.payment_gateway_timeout_seconds,
            )
        except GatewayUnavailable:
            logger.warning(
                "payment.reconcile_gateway_unavailable", extra={"payment_id": str(payment_id)}
            )
            return _GATEWAY_DOWN
        async with AsyncSession(engine) as session:
            applied = await PaymentProcessor(session).apply(
                payment_id, result, try_locks=True, lock_timeout_ms=lock_timeout_ms
            )
        if applied.outcome is not Outcome.PENDING:
            return "applied" if applied.outcome is not Outcome.ALREADY_PROCESSED else "unchanged"
        expires_at = payment.gateway_expires_at
        if (
            result.outcome is VerifyOutcome.PENDING
            and expires_at is not None
            and (now >= expires_at + stale)
        ):
            # The gateway still says pending long after its session ended: give up on it.
            return await _close(engine, payment_id, "abandoned", lock_timeout_ms)
        return "unchanged"
    except BusyError:
        return "unchanged"
    except DBAPIError as error:
        if getattr(error.orig, "sqlstate", None) == LOCK_NOT_AVAILABLE:
            return "unchanged"
        logger.exception("payment.reconcile_failed", extra={"payment_id": str(payment_id)})
        return "failed"
    except Exception:
        logger.exception("payment.reconcile_failed", extra={"payment_id": str(payment_id)})
        return "failed"


async def _close(engine: AsyncEngine, payment_id: UUID, reason: str, lock_timeout_ms: int) -> str:
    """Close a still-pending payment as failed with try-locks; ``unchanged`` if busy."""
    async with AsyncSession(engine) as session, session.begin():
        await session.execute(text(f"SET LOCAL lock_timeout = {int(lock_timeout_ms)}"))
        payment = await session.get(Payment, payment_id)
        assert payment is not None
        if not await session.scalar(order_advisory_lock(payment.order_id, wait=False)):
            return "unchanged"
        order = await lock_order(session, payment.order_id, skip_locked=True)
        payment = await lock_payment(session, payment_id)
        if order is None or payment is None or payment.status != PaymentStatus.PENDING:
            return "unchanged"
        if reason == "request_lost" and payment.gateway_reference is not None:
            return "unchanged"  # init's finish stored it meanwhile
        await close_payment(session, payment, order, reason)
    logger.info("payment.closed", extra={"payment_id": str(payment_id), "reason": reason})
    return "closed"


async def _purge_events(engine: AsyncEngine, before: datetime) -> int:
    """Delete a bounded batch of events past their retention (housekeeping only)."""
    async with AsyncSession(engine) as session, session.begin():
        old = (
            select(PaymentEvent.id)
            .where(PaymentEvent.created_at < before)
            .order_by(PaymentEvent.created_at)
            .limit(EVENT_PURGE_BATCH)
        )
        result = await session.execute(delete(PaymentEvent).where(PaymentEvent.id.in_(old)))
        return int(result.rowcount or 0)  # type: ignore[attr-defined]


Reconcile = Callable[[bool], Awaitable[ReconcileResult]]


async def run_reconciler(reconcile: Reconcile, interval_seconds: float) -> None:
    """Reconcile every ``interval_seconds`` until cancelled; a failed round is logged.

    ``reconcile(purge)`` is asked to trim old events at most once an hour.
    """
    loop = asyncio.get_running_loop()
    last_purge: float | None = None
    while True:
        await asyncio.sleep(interval_seconds)
        purge = last_purge is None or loop.time() - last_purge >= EVENT_PURGE_INTERVAL_SECONDS
        try:
            await reconcile(purge)
        except Exception:
            logger.exception("payment.reconcile_round_failed")
        else:
            if purge:
                last_purge = loop.time()


async def _main() -> None:
    from app.core.config import get_settings
    from app.db.session import create_database_engine
    from app.modules.payments.gateways import build_payment_gateway

    settings = get_settings()
    engine = create_database_engine(settings)
    try:
        gateway = build_payment_gateway(settings, engine)
        print(await reconcile_pending_payments(engine, gateway, settings))  # noqa: T201
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
