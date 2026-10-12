"""Stock counter changes: movements and manual adjustments (INV-02, ADR-029, ADR-034).

Every change of an InventoryItem's counters goes through ``record_movement`` in the same
transaction, under the item's row lock. Reservations (INV-04..06) use it too.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
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
from app.core.time import utc_now
from app.db.models import InventoryItem, MovementType
from app.db.models.inventory import MAX_MOVEMENT_REASON_LENGTH
from app.modules.inventory.holds import release_expired_holds
from app.modules.inventory.movements import Counters, record_movement
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
class AdjustmentResult:
    inventory_item_id: UUID
    variant_id: UUID
    total: int
    reserved: int
    # None when the request changed nothing (a correction to the current total).
    movement_id: UUID | None


def _invalid(field: str, message: str) -> BadRequestError:
    return BadRequestError(
        message="Request validation failed",
        details=[{"field": field, "message": message, "type": "value_error"}],
    )


def _check_quantity(kind: AdjustmentType, quantity: object, field: str = "quantity") -> int:
    minimum = 0 if kind is AdjustmentType.CORRECTION else 1
    if isinstance(quantity, bool) or not isinstance(quantity, int):
        raise _invalid(field, "Must be an integer")
    if not minimum <= quantity <= MAX_STOCK_QUANTITY:
        raise _invalid(field, f"Must be between {minimum} and {MAX_STOCK_QUANTITY}")
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
        now: datetime | None = None,
    ) -> AdjustmentResult:
        """Change a variant's total in the default warehouse; checked under the row lock."""
        quantity = _check_quantity(kind, quantity)
        reason = _check_reason(reason)
        async with self._session.begin():
            item = await self._lock_item(variant_id, now)
            result = await self._adjust_locked(
                item, actor_id, kind, quantity, reason, audit_request
            )
        if result.movement_id is not None:
            logger.info(
                "inventory.adjusted",
                extra={"variant_id": str(variant_id), "type": kind.value, "total": result.total},
            )
        return result

    async def apply_update(
        self,
        *,
        actor_id: UUID | None,
        variant_id: UUID,
        adjustment: tuple[AdjustmentType, int] | None,
        low_stock_threshold: int | None,
        reason: str,
        expected_total: int | None = None,
        audit_request: Request | None = None,
        now: datetime | None = None,
    ) -> AdjustmentResult:
        """The admin PATCH (INV-08): an adjustment and/or a new threshold.

        Runs in the caller's transaction, so the caller can read the result back under the
        same row lock. ``expected_total`` is compared under the lock, before any change, with
        the default-warehouse total (the only warehouse in v1, ADR-005).
        """
        reason = _check_reason(reason)
        if adjustment is not None:
            adjustment = (adjustment[0], _check_quantity(*adjustment))
        if low_stock_threshold is not None:
            low_stock_threshold = _check_quantity(
                AdjustmentType.CORRECTION, low_stock_threshold, "low_stock_threshold"
            )
        item = await self._lock_item(variant_id, now)
        if expected_total is not None and item.total_quantity != expected_total:
            raise ConflictError(
                message="Stock changed since it was read",
                details=[{"field": "expected_total", "type": "stale_total"}],
            )
        if low_stock_threshold is not None and low_stock_threshold != item.low_stock_threshold:
            before_threshold = item.low_stock_threshold
            item.low_stock_threshold = low_stock_threshold
            await self._session.flush()
            await record_audit(
                self._session,
                actor_id=actor_id,
                action="inventory.threshold_updated",
                entity_type="inventory_item",
                entity_id=item.id,
                before={"low_stock_threshold": before_threshold},
                after={"low_stock_threshold": low_stock_threshold, "reason": reason},
                request=audit_request,
            )
        if adjustment is None:
            counters = Counters.of(item)
            return AdjustmentResult(item.id, variant_id, counters.total, counters.reserved, None)
        return await self._adjust_locked(
            item, actor_id, adjustment[0], adjustment[1], reason, audit_request
        )

    async def _lock_item(self, variant_id: UUID, now: datetime | None) -> InventoryItem:
        """Lock order of every stock write: variant (SHARE) → item (UPDATE) (ADR-034)."""
        product_id = await self._repository.variant_product_id(variant_id)
        if product_id is None:
            raise NotFoundError(message="Variant not found")
        item = await self._repository.lock_default_item(variant_id, product_id)
        # Units of expired reservations are free again, job or not (ADR-036).
        await release_expired_holds(self._session, [item], now or utc_now())
        return item

    async def _adjust_locked(
        self,
        item: InventoryItem,
        actor_id: UUID | None,
        kind: AdjustmentType,
        quantity: int,
        reason: str,
        audit_request: Request | None,
    ) -> AdjustmentResult:
        before = Counters.of(item)
        total = _new_total(kind, before, quantity)
        if total == before.total:
            # Only a correction to the current count gets here: nothing to record.
            return AdjustmentResult(item.id, item.variant_id, before.total, before.reserved, None)
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
        return AdjustmentResult(item.id, item.variant_id, total, before.reserved, movement.id)
