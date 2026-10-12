"""Stock reservations for orders: reserve (INV-04), commit and release (INV-05), and
``expire`` for the cleanup job (INV-06, ``jobs.py``).
PRD «موجودی و رزرو» ✓, ADR-007, ADR-029, ADR-034, ADR-036.

Rules:
- A reservation is valid in ``[created, expires_at)``. Once ``expires_at <= now`` it holds
  nothing for any check, whether or not the cleanup job has run yet.
- Lock order on every path: variants (``FOR SHARE``) → inventory_items (``FOR UPDATE``,
  ``ORDER BY variant_id, warehouse_id``) → reservation rows (``FOR UPDATE``). No cycle.
- A reservation item's status changes only under its inventory item's lock, so a counter
  is moved at most once per item, whoever releases it.
- ``reserve`` runs in the caller's transaction (ORD-04 creates the order in the same one)
  and never commits; any error rolls the whole reservation back (all-or-nothing).
- ``commit`` and ``release`` also run in the caller's transaction. Both are idempotent and
  decide only after taking the locks. An expired ``commit`` frees the stock and *returns*
  ``EXPIRED`` instead of raising, so the release survives the caller's commit (PAY-03 raises
  ``RESERVATION_EXPIRED`` afterwards).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    BadRequestError,
    BusinessRuleError,
    ConflictError,
    ErrorCode,
    NotFoundError,
)
from app.core.time import utc_now
from app.db.models import (
    InventoryItem,
    InventoryReservation,
    InventoryReservationItem,
    MovementType,
    Product,
    ProductStatus,
    ProductVariant,
    ReservationItemStatus,
    ReservationStatus,
)
from app.db.models.common import not_deleted
from app.db.models.inventory import DEFAULT_WAREHOUSE_ID, MAX_MOVEMENT_REASON_LENGTH
from app.modules.inventory.holds import EXPIRED_REASON, release_expired_holds, release_item
from app.modules.inventory.movements import Counters, record_movement
from app.shared.audit import record_audit
from app.shared.inventory import MAX_STOCK_QUANTITY

logger = logging.getLogger(__name__)

# ADR-007: stock is held for 15 minutes from POST /orders.
RESERVATION_TTL: Final = timedelta(minutes=15)
MAX_RESERVATION_LINES: Final = 100
# Namespace of the per-order advisory lock (the cleanup job uses its own key).
ORDER_LOCK_NAMESPACE: Final = 73_011


@dataclass(frozen=True, slots=True)
class ReserveLine:
    variant_id: UUID
    quantity: int


@dataclass(frozen=True, slots=True)
class ReservationResult:
    reservation_id: UUID
    expires_at: datetime
    # False when an identical active reservation of the order was returned (idempotent).
    created: bool


class CommitOutcome(StrEnum):
    COMMITTED = "committed"
    # Committed earlier: nothing changed (idempotent).
    ALREADY_COMMITTED = "already_committed"
    # Expired or released: never consumed. Any stock it still held is free now.
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class CommitResult:
    reservation_id: UUID
    outcome: CommitOutcome

    def raise_for_expired(self) -> None:
        """409 ``RESERVATION_EXPIRED``; call it after committing the caller's transaction."""
        if self.outcome is CommitOutcome.EXPIRED:
            raise ConflictError(
                code=ErrorCode.RESERVATION_EXPIRED, message="The reservation has expired"
            )


class ReleaseOutcome(StrEnum):
    RELEASED = "released"
    # Released or expired earlier: nothing changed (idempotent).
    ALREADY_CLOSED = "already_closed"


@dataclass(frozen=True, slots=True)
class ReleaseResult:
    reservation_id: UUID
    outcome: ReleaseOutcome


def _invalid(message: str) -> BadRequestError:
    return BadRequestError(
        message="Request validation failed",
        details=[{"field": "lines", "message": message, "type": "value_error"}],
    )


def merge_lines(lines: Iterable[ReserveLine]) -> dict[UUID, int]:
    """Quantity per variant; duplicates are added up. Invalid input is a 400."""
    wanted: dict[UUID, int] = {}
    for line in lines:
        quantity = line.quantity
        if isinstance(quantity, bool) or not isinstance(quantity, int):
            raise _invalid("quantity must be an integer")
        if not 1 <= quantity <= MAX_STOCK_QUANTITY:
            raise _invalid(f"quantity must be between 1 and {MAX_STOCK_QUANTITY}")
        if not isinstance(line.variant_id, UUID):
            raise _invalid("variant_id must be a UUID")
        wanted[line.variant_id] = wanted.get(line.variant_id, 0) + quantity
    if not wanted:
        raise _invalid("at least one line is required")
    if len(wanted) > MAX_RESERVATION_LINES:
        raise _invalid(f"at most {MAX_RESERVATION_LINES} variants")
    if any(quantity > MAX_STOCK_QUANTITY for quantity in wanted.values()):
        raise _invalid(f"quantity must be at most {MAX_STOCK_QUANTITY} per variant")
    return wanted


def _order_key(order_id: UUID) -> int:
    """A signed 32-bit key from the order id for the two-key advisory lock."""
    return int.from_bytes(order_id.bytes[:4], "big", signed=True)


def _usable(variant: ProductVariant | None) -> bool:
    return (
        variant is not None
        and variant.is_active
        and variant.is_purchasable
        and variant.base_price is not None
    )


class ReservationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def reserve(
        self,
        *,
        order_id: UUID,
        lines: Sequence[ReserveLine],
        user_id: UUID | None,
        cart_id: UUID | None = None,
        now: datetime | None = None,
    ) -> ReservationResult:
        """Hold stock for an order, all-or-nothing; idempotent per order (ADR-036)."""
        if not self._session.in_transaction():
            raise RuntimeError("reserve() must run inside the caller's transaction")
        wanted = merge_lines(lines)
        now = now or utc_now()

        # First lock of all, taken only here: calls for the same order run one at a time,
        # so the checks below cannot race and the unique index never fires (ADR-036).
        await self._session.execute(
            select(func.pg_advisory_xact_lock(ORDER_LOCK_NAMESPACE, _order_key(order_id)))
        )
        # One read of the order's live reservation (the unique index allows one): a commit
        # landing between two separate reads would otherwise let a second one be inserted.
        existing = await self._live_for_order(order_id)
        if existing is not None and existing.status == ReservationStatus.COMMITTED:
            raise ConflictError(
                code=ErrorCode.RESERVATION_ALREADY_CONSUMED,
                message="The order's reservation was already committed",
            )
        if existing is not None and now < existing.expires_at:
            return await self._same_or_conflict(existing, wanted)

        await self._check_variants(sorted(wanted))
        stale_items = [] if existing is None else await self._item_ids_of(existing.id)
        items = await self._lock_items(sorted(wanted), stale_items)

        await release_expired_holds(self._session, items.values(), now)
        if existing is not None:
            # Expired: its items were all in the lock set and are released by now.
            await self._expire(existing, now)

        by_variant = {
            item.variant_id: item
            for item in items.values()
            if item.warehouse_id == DEFAULT_WAREHOUSE_ID and item.variant_id in wanted
        }
        short = sorted(
            variant_id
            for variant_id, quantity in wanted.items()
            if (item := by_variant.get(variant_id)) is None
            or item.total_quantity - item.reserved_quantity < quantity
        )
        if short:
            raise ConflictError(
                code=ErrorCode.INSUFFICIENT_STOCK,
                message="Not enough stock",
                details=[{"variant_id": str(v), "type": "insufficient_stock"} for v in short],
            )

        reservation = InventoryReservation(
            order_id=order_id,
            cart_id=cart_id,
            user_id=user_id,
            status=ReservationStatus.ACTIVE,
            expires_at=now + RESERVATION_TTL,
        )
        self._session.add(reservation)
        await self._session.flush()
        for variant_id in sorted(wanted):
            item, quantity = by_variant[variant_id], wanted[variant_id]
            before = Counters.of(item)
            item.reserved_quantity += quantity
            self._session.add(
                InventoryReservationItem(
                    reservation_id=reservation.id,
                    inventory_item_id=item.id,
                    product_id=item.product_id,
                    variant_id=variant_id,
                    quantity=quantity,
                )
            )
            await self._session.flush()
            await record_movement(
                self._session,
                item,
                movement_type=MovementType.RESERVE,
                quantity=quantity,
                before=before,
                actor_id=user_id,
                reference=("reservation", reservation.id),
            )
        await record_audit(
            self._session,
            actor_id=user_id,
            action="reservation.created",
            entity_type="inventory_reservation",
            entity_id=reservation.id,
            before=None,
            after={
                "order_id": order_id,
                "expires_at": reservation.expires_at,
                "lines": {str(variant_id): wanted[variant_id] for variant_id in sorted(wanted)},
            },
            request=None,
        )
        logger.info(
            "reservation.created",
            extra={"reservation_id": str(reservation.id), "lines": len(wanted)},
        )
        return ReservationResult(reservation.id, reservation.expires_at, created=True)

    async def commit(
        self,
        reservation_id: UUID,
        *,
        actor_id: UUID | None = None,
        now: datetime | None = None,
    ) -> CommitResult:
        """Consume the held stock for good (payment succeeded); idempotent (ADR-036).

        An expired reservation is never consumed: what it still holds is released here and
        ``EXPIRED`` is returned, for the caller to commit and then report as a 409.
        The caller MUST branch on ``outcome`` (or call ``raise_for_expired``): treating
        ``EXPIRED`` as success would mark an order paid with no stock taken (PAY-03).
        """
        if not self._session.in_transaction():
            raise RuntimeError("commit() must run inside the caller's transaction")
        reservation, items, held = await self._locked(reservation_id)
        # After the lock wait: a commit that waited must not pass an expiry meanwhile.
        now = now or utc_now()

        if reservation.status == ReservationStatus.COMMITTED:
            return CommitResult(reservation.id, CommitOutcome.ALREADY_COMMITTED)
        if reservation.status != ReservationStatus.ACTIVE:
            return CommitResult(reservation.id, CommitOutcome.EXPIRED)
        active = [line for line in held if line.status == ReservationItemStatus.ACTIVE]
        if now >= reservation.expires_at or len(active) != len(held):
            # Past expires_at, or a writer already freed part of it lazily (which happens
            # only once it expired): close it as expired, never consume it.
            for line in active:
                await release_item(
                    self._session, items[line.inventory_item_id], line, now, EXPIRED_REASON
                )
            await self._close(reservation, ReservationStatus.EXPIRED, now, actor_id=None)
            return CommitResult(reservation.id, CommitOutcome.EXPIRED)

        for line in held:
            item = items[line.inventory_item_id]
            before = Counters.of(item)
            # Both counters drop together, in the item's single UPDATE.
            item.total_quantity -= line.quantity
            item.reserved_quantity -= line.quantity
            line.status = ReservationItemStatus.COMMITTED
            await self._session.flush()
            await record_movement(
                self._session,
                item,
                movement_type=MovementType.COMMIT,
                quantity=line.quantity,
                before=before,
                actor_id=actor_id,
                reference=("reservation", reservation.id),
            )
        await self._close(reservation, ReservationStatus.COMMITTED, now, actor_id=actor_id)
        return CommitResult(reservation.id, CommitOutcome.COMMITTED)

    async def release(
        self,
        reservation_id: UUID,
        *,
        reason: str,
        actor_id: UUID | None = None,
        now: datetime | None = None,
    ) -> ReleaseResult:
        """Give the held stock back (payment failed, order cancelled); idempotent.

        A committed reservation cannot be released: 409 ``RESERVATION_ALREADY_CONSUMED``.
        """
        if not self._session.in_transaction():
            raise RuntimeError("release() must run inside the caller's transaction")
        reason = reason.strip() if isinstance(reason, str) else ""
        if not 1 <= len(reason) <= MAX_MOVEMENT_REASON_LENGTH:
            raise BadRequestError(
                message="Request validation failed",
                details=[
                    {
                        "field": "reason",
                        "message": f"reason must be 1 to {MAX_MOVEMENT_REASON_LENGTH} characters",
                        "type": "value_error",
                    }
                ],
            )
        reservation, items, held = await self._locked(reservation_id)
        now = now or utc_now()

        if reservation.status == ReservationStatus.COMMITTED:
            raise ConflictError(
                code=ErrorCode.RESERVATION_ALREADY_CONSUMED,
                message="The reservation was already committed",
            )
        if reservation.status != ReservationStatus.ACTIVE:
            return ReleaseResult(reservation.id, ReleaseOutcome.ALREADY_CLOSED)
        for line in held:
            if line.status == ReservationItemStatus.ACTIVE:
                await release_item(
                    self._session, items[line.inventory_item_id], line, now, reason, actor_id
                )
        await self._close(
            reservation,
            ReservationStatus.RELEASED,
            now,
            actor_id=actor_id,
            # Released by the caller after it had already expired (reports tell them apart).
            extra={"reason": reason, "expired": now >= reservation.expires_at},
        )
        return ReleaseResult(reservation.id, ReleaseOutcome.RELEASED)

    async def expire(self, reservation_id: UUID, *, now: datetime | None = None) -> bool:
        """Close one expired reservation for the cleanup job (INV-06); True if closed.

        Never raises for a state it finds; it skips (False) a reservation that is gone,
        no longer active or not yet expired, and one whose row another transaction holds.
        Item locks are waited for (the job bounds that wait with ``lock_timeout``).
        Correctness never depends on this running (ADR-036).
        """
        if not self._session.in_transaction():
            raise RuntimeError("expire() must run inside the caller's transaction")
        try:
            locked = await self._lock_reservation(reservation_id, skip_locked=True)
        except NotFoundError:
            return False
        if locked is None:
            return False
        reservation, items, held = locked
        now = now or utc_now()
        if reservation.status != ReservationStatus.ACTIVE or now < reservation.expires_at:
            return False
        for line in held:
            if line.status == ReservationItemStatus.ACTIVE:
                await release_item(
                    self._session, items[line.inventory_item_id], line, now, EXPIRED_REASON
                )
        await self._close(reservation, ReservationStatus.EXPIRED, now, actor_id=None)
        return True

    # --- helpers -----------------------------------------------------------------------

    async def _lock_reservation(
        self, reservation_id: UUID, *, skip_locked: bool = False
    ) -> (
        tuple[InventoryReservation, dict[UUID, InventoryItem], list[InventoryReservationItem]]
        | None
    ):
        """Lock a reservation's inventory items, then its row, in the ADR-036 order.

        A reservation's set of items never changes, so reading it before the locks is
        safe; everything else is read again after them. With ``skip_locked`` (the cleanup
        job) a reservation row another transaction holds is skipped: ``None``.
        """
        item_ids = await self._item_ids_of(reservation_id)
        if not item_ids:
            # Every reservation has at least one item, so this one does not exist.
            raise NotFoundError(message="Reservation not found")
        statement = (
            select(InventoryItem)
            .where(InventoryItem.id.in_(item_ids))
            .order_by(InventoryItem.variant_id, InventoryItem.warehouse_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        items = {item.id: item for item in await self._session.scalars(statement)}
        reservation = await self._session.scalar(
            select(InventoryReservation)
            .where(InventoryReservation.id == reservation_id)
            .with_for_update(skip_locked=skip_locked)
            .execution_options(populate_existing=True)
        )
        if reservation is None:
            if skip_locked:
                return None
            raise NotFoundError(message="Reservation not found")
        held = list(
            await self._session.scalars(
                select(InventoryReservationItem)
                .where(InventoryReservationItem.reservation_id == reservation_id)
                .order_by(InventoryReservationItem.variant_id)
                .execution_options(populate_existing=True)
            )
        )
        return reservation, items, held

    async def _locked(
        self, reservation_id: UUID
    ) -> tuple[InventoryReservation, dict[UUID, InventoryItem], list[InventoryReservationItem]]:
        locked = await self._lock_reservation(reservation_id)
        assert locked is not None  # only skip_locked returns None
        return locked

    async def _close(
        self,
        reservation: InventoryReservation,
        status: ReservationStatus,
        now: datetime,
        *,
        actor_id: UUID | None,
        extra: Mapping[str, object] | None = None,
    ) -> None:
        """Move a locked, active reservation whose items are settled to its final status."""
        reservation.status = status
        if status == ReservationStatus.COMMITTED:
            reservation.committed_at = now
        else:
            reservation.released_at = now
        await self._session.flush()
        after: dict[str, object] = {"status": status.value, **(extra or {})}
        await record_audit(
            self._session,
            actor_id=actor_id,
            action=f"reservation.{status.value}",
            entity_type="inventory_reservation",
            entity_id=reservation.id,
            before={"status": ReservationStatus.ACTIVE.value},
            after=after,
            request=None,
        )
        logger.info(f"reservation.{status.value}", extra={"reservation_id": str(reservation.id)})

    async def _live_for_order(self, order_id: UUID) -> InventoryReservation | None:
        """The order's active or committed reservation, if any."""
        statement = (
            select(InventoryReservation)
            .where(
                InventoryReservation.order_id == order_id,
                InventoryReservation.status.in_(
                    [ReservationStatus.ACTIVE, ReservationStatus.COMMITTED]
                ),
            )
            .execution_options(populate_existing=True)
        )
        return (await self._session.scalars(statement)).one_or_none()

    async def _same_or_conflict(
        self, reservation: InventoryReservation, wanted: Mapping[UUID, int]
    ) -> ReservationResult:
        statement = select(
            InventoryReservationItem.variant_id, InventoryReservationItem.quantity
        ).where(InventoryReservationItem.reservation_id == reservation.id)
        held: dict[UUID, int] = {}
        for variant_id, quantity in await self._session.execute(statement):
            held[variant_id] = held.get(variant_id, 0) + quantity
        if held != dict(wanted):
            raise ConflictError(message="The order already has a different reservation")
        return ReservationResult(reservation.id, reservation.expires_at, created=False)

    async def _check_variants(self, variant_ids: list[UUID]) -> None:
        """Share-lock the variants (a concurrent delete waits) and require them sellable."""
        statement = (
            select(ProductVariant)
            .join(Product, Product.id == ProductVariant.product_id)
            .where(
                ProductVariant.id.in_(variant_ids),
                not_deleted(ProductVariant),
                # SD rule: only variants of a published, live product can be bought.
                Product.status == ProductStatus.PUBLISHED,
                not_deleted(Product),
            )
            .order_by(ProductVariant.id)
            .with_for_update(read=True, of=ProductVariant)
            .execution_options(populate_existing=True)
        )
        found = {variant.id: variant for variant in await self._session.scalars(statement)}
        unusable = [variant_id for variant_id in variant_ids if not _usable(found.get(variant_id))]
        if unusable:
            raise BusinessRuleError(
                message="Some variants cannot be bought",
                details=[{"variant_id": str(v), "type": "not_purchasable"} for v in unusable],
            )

    async def _item_ids_of(self, reservation_id: UUID) -> list[UUID]:
        statement = select(InventoryReservationItem.inventory_item_id).where(
            InventoryReservationItem.reservation_id == reservation_id
        )
        return list((await self._session.scalars(statement)).all())

    async def _lock_items(
        self, variant_ids: list[UUID], extra_ids: list[UUID]
    ) -> dict[UUID, InventoryItem]:
        """Default-warehouse items of the variants plus ``extra_ids``, in one ordered lock."""
        condition = (InventoryItem.variant_id.in_(variant_ids)) & (
            InventoryItem.warehouse_id == DEFAULT_WAREHOUSE_ID
        )
        if extra_ids:
            condition = condition | InventoryItem.id.in_(extra_ids)
        statement = (
            select(InventoryItem)
            .where(condition)
            .order_by(InventoryItem.variant_id, InventoryItem.warehouse_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return {item.id: item for item in await self._session.scalars(statement)}

    async def _expire(self, reservation: InventoryReservation, now: datetime) -> None:
        """Close an expired reservation whose items are all locked and already released."""
        locked = await self._session.scalar(
            select(InventoryReservation)
            .where(InventoryReservation.id == reservation.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if locked is not None and locked.status == ReservationStatus.COMMITTED:
            # A commit won the item locks after this call saw the reservation as expired
            # (its ``now`` was later); creating a second one would break the unique index.
            raise ConflictError(
                code=ErrorCode.RESERVATION_ALREADY_CONSUMED,
                message="The order's reservation was already committed",
            )
        if locked is None or locked.status != ReservationStatus.ACTIVE:
            return
        still_held = await self._session.scalar(
            select(func.count())
            .select_from(InventoryReservationItem)
            .where(
                InventoryReservationItem.reservation_id == locked.id,
                InventoryReservationItem.status == ReservationItemStatus.ACTIVE,
            )
        )
        if still_held:
            # The lock set must have covered all its items (ADR-036); fail loudly if not.
            raise RuntimeError(f"reservation {locked.id} still holds items")
        locked.status = ReservationStatus.EXPIRED
        locked.released_at = now
        await self._session.flush()
        await record_audit(
            self._session,
            actor_id=None,
            action="reservation.expired",
            entity_type="inventory_reservation",
            entity_id=locked.id,
            before={"status": ReservationStatus.ACTIVE.value},
            after={"status": ReservationStatus.EXPIRED.value},
            request=None,
        )
