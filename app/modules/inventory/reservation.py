"""Stock reservations for orders (INV-04; INV-05 and INV-06 add commit, release and the
cleanup job). PRD «موجودی و رزرو» ✓, ADR-007, ADR-029, ADR-034, ADR-036.

Rules:
- A reservation is valid in ``[created, expires_at)``. Once ``expires_at <= now`` it holds
  nothing for any check, whether or not the cleanup job has run yet.
- Lock order on every path: variants (``FOR SHARE``) → inventory_items (``FOR UPDATE``,
  ``ORDER BY variant_id, warehouse_id``) → reservation rows (``FOR UPDATE``). No cycle.
- A reservation item's status changes only under its inventory item's lock, so a counter
  is moved at most once per item, whoever releases it.
- ``reserve`` runs in the caller's transaction (ORD-04 creates the order in the same one)
  and never commits; any error rolls the whole reservation back (all-or-nothing).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BadRequestError, BusinessRuleError, ConflictError, ErrorCode
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
from app.db.models.inventory import DEFAULT_WAREHOUSE_ID
from app.modules.inventory.holds import release_expired_holds
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
        if await self._has_committed(order_id):
            raise ConflictError(
                code=ErrorCode.RESERVATION_ALREADY_CONSUMED,
                message="The order's reservation was already committed",
            )
        existing = await self._active_for_order(order_id)
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

    # --- helpers -----------------------------------------------------------------------

    async def _has_committed(self, order_id: UUID) -> bool:
        statement = select(InventoryReservation.id).where(
            InventoryReservation.order_id == order_id,
            InventoryReservation.status == ReservationStatus.COMMITTED,
        )
        return (await self._session.scalar(statement.limit(1))) is not None

    async def _active_for_order(self, order_id: UUID) -> InventoryReservation | None:
        statement = (
            select(InventoryReservation)
            .where(
                InventoryReservation.order_id == order_id,
                InventoryReservation.status == ReservationStatus.ACTIVE,
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
