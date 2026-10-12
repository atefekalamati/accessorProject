"""Counter snapshots and movement rows shared by every stock write (INV-02, ADR-034)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import InventoryItem, InventoryMovement, MovementType


@dataclass(frozen=True, slots=True)
class Counters:
    total: int
    reserved: int

    @classmethod
    def of(cls, item: InventoryItem) -> Counters:
        return cls(total=item.total_quantity, reserved=item.reserved_quantity)


async def record_movement(
    session: AsyncSession,
    item: InventoryItem,
    *,
    movement_type: MovementType,
    quantity: int,
    before: Counters,
    actor_id: UUID | None,
    reason: str | None = None,
    reference: tuple[str, UUID] | None = None,
) -> InventoryMovement:
    """Add the movement for a change already applied to ``item`` (locked by the caller)."""
    movement = InventoryMovement(
        inventory_item_id=item.id,
        movement_type=movement_type,
        quantity=quantity,
        total_before=before.total,
        total_after=item.total_quantity,
        reserved_before=before.reserved,
        reserved_after=item.reserved_quantity,
        reference_type=None if reference is None else reference[0],
        reference_id=None if reference is None else reference[1],
        reason=reason,
        created_by=actor_id,
    )
    session.add(movement)
    await session.flush()
    return movement
