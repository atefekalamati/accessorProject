"""Stock counter changes: movements and manual adjustments (INV-02, ADR-029, ADR-034).

Every change of an InventoryItem's counters goes through ``record_movement`` in the same
transaction, under the item's row lock. Reservations (INV-04..06) use it too.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    BadRequestError,
    BusinessRuleError,
    ConflictError,
    ErrorCode,
    NotFoundError,
)
from app.db.models import InventoryItem, InventoryMovement, MovementType
from app.db.models.inventory import MAX_MOVEMENT_REASON_LENGTH
from app.modules.inventory.repository import InventoryRepository
from app.shared.audit import record_audit
from app.shared.inventory import MAX_STOCK_QUANTITY

logger = logging.getLogger(__name__)


class AdjustmentType(StrEnum):
    """Manual changes of the total (PRD stockAdjustmentType)."""

    INCREASE = MovementType.INCREASE.value
    DECREASE = MovementType.DECREASE.value
    # Sets the total to an absolute count (e.g. after a stocktake).
    CORRECTION = MovementType.CORRECTION.value


@dataclass(frozen=True, slots=True)
class Counters:
    total: int
    reserved: int

    @classmethod
    def of(cls, item: InventoryItem) -> Counters:
        return cls(total=item.total_quantity, reserved=item.reserved_quantity)


@dataclass(frozen=True, slots=True)
class AdjustmentResult:
    inventory_item_id: UUID
    variant_id: UUID
    total: int
    reserved: int
    # None when the request changed nothing (a correction to the current total).
    movement_id: UUID | None


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


def _invalid(field: str, message: str) -> BadRequestError:
    return BadRequestError(
        message="Request validation failed",
        details=[{"field": field, "message": message, "type": "value_error"}],
    )


def _check_quantity(kind: AdjustmentType, quantity: object) -> int:
    minimum = 0 if kind is AdjustmentType.CORRECTION else 1
    if isinstance(quantity, bool) or not isinstance(quantity, int):
        raise _invalid("quantity", "Must be an integer")
    if not minimum <= quantity <= MAX_STOCK_QUANTITY:
        raise _invalid("quantity", f"Must be between {minimum} and {MAX_STOCK_QUANTITY}")
    return quantity


def _check_reason(reason: object) -> str:
    if not isinstance(reason, str):
        raise _invalid("reason", "Must be a string")
    cleaned = reason.strip()
    if not 1 <= len(cleaned) <= MAX_MOVEMENT_REASON_LENGTH:
        raise _invalid("reason", f"Required, at most {MAX_MOVEMENT_REASON_LENGTH} characters")
    return cleaned


def _new_total(kind: AdjustmentType, current: Counters, quantity: int) -> int:
    if kind is AdjustmentType.INCREASE:
        total = current.total + quantity
        if total > MAX_STOCK_QUANTITY:
            raise BusinessRuleError(
                message=f"Stock cannot exceed {MAX_STOCK_QUANTITY} units",
                details=[{"field": "quantity", "type": "stock_limit"}],
            )
        return total
    total = current.total - quantity if kind is AdjustmentType.DECREASE else quantity
    if total < current.reserved:
        # Units held by active reservations cannot be removed (ADR-029).
        raise ConflictError(
            code=ErrorCode.INSUFFICIENT_STOCK,
            message="Stock cannot go below the reserved quantity",
            details=[{"field": "quantity", "type": "below_reserved"}],
        )
    return total


class InventoryService:
    def __init__(self, session: AsyncSession, repository: InventoryRepository) -> None:
        self._session = session
        self._repository = repository

    async def adjust(
        self,
        *,
        actor_id: UUID | None,
        variant_id: UUID,
        kind: AdjustmentType,
        quantity: int,
        reason: str,
        audit_request: Request | None = None,
    ) -> AdjustmentResult:
        """Change a variant's total in the default warehouse; checked under the row lock."""
        quantity = _check_quantity(kind, quantity)
        reason = _check_reason(reason)
        async with self._session.begin():
            product_id = await self._repository.variant_product_id(variant_id)
            if product_id is None:
                raise NotFoundError(message="Variant not found")
            item = await self._repository.lock_default_item(variant_id, product_id)
            before = Counters.of(item)
            total = _new_total(kind, before, quantity)
            if total == before.total:
                # Only a correction to the current count gets here: nothing to record.
                return AdjustmentResult(item.id, variant_id, before.total, before.reserved, None)
            item.total_quantity = total
            await self._session.flush()
            movement = await record_movement(
                self._session,
                item,
                movement_type=MovementType(kind.value),
                quantity=abs(total - before.total),
                before=before,
                actor_id=actor_id,
                reason=reason,
            )
            await record_audit(
                self._session,
                actor_id=actor_id,
                action="inventory.adjusted",
                entity_type="inventory_item",
                entity_id=item.id,
                before={"total_quantity": before.total},
                after={
                    "total_quantity": total,
                    "adjustment_type": kind.value,
                    "reason": reason,
                    "movement_id": movement.id,
                },
                request=audit_request,
            )
            result = AdjustmentResult(item.id, variant_id, total, before.reserved, movement.id)
        logger.info(
            "inventory.adjusted",
            extra={"variant_id": str(variant_id), "type": kind.value, "total": total},
        )
        return result
