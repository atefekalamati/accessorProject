"""Expired reservation holds (INV-04, ADR-036).

A reservation stops holding stock at ``expires_at``, whether or not the cleanup job (INV-06)
has run. Two consequences, used everywhere stock is read or written:

- writers free the expired holds on the items they have locked (``release_expired_holds``)
  before checking stock, under the same row locks;
- read-only views add the still-recorded expired holds back to the free stock
  (``expired_holds``), so a late cleanup never hides stock.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    InventoryItem,
    InventoryReservation,
    InventoryReservationItem,
    MovementType,
    ReservationItemStatus,
    ReservationStatus,
)
from app.modules.inventory.movements import Counters, record_movement

EXPIRED_REASON: Final = "expired"


def _expired_hold(now: datetime) -> list[ColumnElement[bool]]:
    return [
        InventoryReservationItem.status == ReservationItemStatus.ACTIVE,
        InventoryReservation.status == ReservationStatus.ACTIVE,
        # Valid in [created, expires_at): at expires_at it no longer holds anything.
        InventoryReservation.expires_at <= now,
    ]


def expired_hold_sum(item_id: Any, now: datetime) -> Any:
    """Correlated SQL: units on ``item_id`` still recorded for expired reservations."""
    return (
        select(func.coalesce(func.sum(InventoryReservationItem.quantity), 0))
        .join(
            InventoryReservation,
            InventoryReservation.id == InventoryReservationItem.reservation_id,
        )
        .where(InventoryReservationItem.inventory_item_id == item_id, *_expired_hold(now))
        .scalar_subquery()
    )


async def expired_holds(
    session: AsyncSession, item_ids: Collection[UUID], now: datetime
) -> dict[UUID, int]:
    """Units per item that expired reservations still hold (one grouped query)."""
    if not item_ids:
        return {}
    statement = (
        select(
            InventoryReservationItem.inventory_item_id, func.sum(InventoryReservationItem.quantity)
        )
        .join(
            InventoryReservation,
            InventoryReservation.id == InventoryReservationItem.reservation_id,
        )
        .where(InventoryReservationItem.inventory_item_id.in_(item_ids), *_expired_hold(now))
        .group_by(InventoryReservationItem.inventory_item_id)
    )
    return {item_id: int(total) for item_id, total in await session.execute(statement)}


async def release_expired_holds(
    session: AsyncSession, items: Iterable[InventoryItem], now: datetime
) -> None:
    """Free what expired reservations hold on ``items``; the caller holds their row locks.

    Only the reservation *items* change (each under its inventory item's lock); the
    reservation row is closed later by commit, release or the job. The movement is the
    record of this release (no audit row; ADR-036).
    """
    by_id = {item.id: item for item in items}
    if not by_id:
        return
    statement = (
        select(InventoryReservationItem)
        .join(
            InventoryReservation,
            InventoryReservation.id == InventoryReservationItem.reservation_id,
        )
        .where(InventoryReservationItem.inventory_item_id.in_(by_id), *_expired_hold(now))
        .order_by(InventoryReservationItem.inventory_item_id, InventoryReservationItem.id)
        .execution_options(populate_existing=True)
    )
    for held in await session.scalars(statement):
        await release_item(session, by_id[held.inventory_item_id], held, now, EXPIRED_REASON)


async def release_item(
    session: AsyncSession,
    item: InventoryItem,
    held: InventoryReservationItem,
    now: datetime,
    reason: str,
    actor_id: UUID | None = None,
) -> None:
    """Give one held line back to ``item`` (locked by the caller)."""
    before = Counters.of(item)
    item.reserved_quantity -= held.quantity
    held.status = ReservationItemStatus.RELEASED
    held.released_at = now
    await session.flush()
    await record_movement(
        session,
        item,
        movement_type=MovementType.RELEASE,
        quantity=held.quantity,
        before=before,
        actor_id=actor_id,
        reason=reason,
        reference=("reservation", held.reservation_id),
    )
