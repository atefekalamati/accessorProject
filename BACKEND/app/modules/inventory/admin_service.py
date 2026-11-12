"""Admin inventory views and the stock PATCH (INV-08, ADR-038)."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.time import utc_now
from app.db.models import ReservationItemStatus, ReservationStatus
from app.modules.auth.service import CurrentUser
from app.modules.inventory.admin_repository import (
    AdminInventoryRepository,
    InventoryFilters,
    ReservationQuery,
)
from app.modules.inventory.admin_schemas import (
    InventoryRow,
    MovementRow,
    ReservationItemRow,
    ReservationRow,
    UpdateInventoryRequest,
)
from app.modules.inventory.repository import InventoryRepository
from app.modules.inventory.service import InventoryService
from app.shared.pagination import Page, PageParams

logger = logging.getLogger(__name__)

READ_PERMISSIONS: Final = ("inventory:read", "inventory:update")
UPDATE_PERMISSION: Final = "inventory:update"
EXPIRED: Final = ReservationStatus.EXPIRED.value


def _row(row: Any) -> InventoryRow:
    return InventoryRow.model_validate(row, from_attributes=True)


def _variant_not_found() -> NotFoundError:
    return NotFoundError(message="Variant not found")


class AdminInventoryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repository = AdminInventoryRepository(session)

    async def list_stock(
        self,
        filters: InventoryFilters,
        sort: str,
        params: PageParams,
        now: datetime | None = None,
    ) -> Page[InventoryRow]:
        async with self._session.begin():
            rows, total = await self._repository.list_stock(filters, sort, params, now or utc_now())
        return Page.build([_row(row) for row in rows], total=total, params=params)

    async def update(
        self,
        actor: CurrentUser,
        variant_id: UUID,
        payload: UpdateInventoryRequest,
        request: Request,
    ) -> InventoryRow:
        adjustment = (
            None
            if payload.adjustment_type is None or payload.quantity is None
            else (payload.adjustment_type, payload.quantity)
        )
        now = utc_now()
        async with self._session.begin():
            result = await InventoryService(
                self._session, InventoryRepository(self._session)
            ).apply_update(
                actor_id=actor.id,
                variant_id=variant_id,
                adjustment=adjustment,
                low_stock_threshold=payload.low_stock_threshold,
                reason=payload.reason,
                expected_total=payload.expected_total,
                audit_request=request,
                now=now,
            )
            # Read back under the row locks still held: the response is what was written.
            row = await self._repository.stock_row(variant_id, now)
        if row is None:  # the variant is share-locked above; kept for the type checker
            raise _variant_not_found()
        logger.info(
            "inventory.updated",
            extra={
                "variant_id": str(variant_id),
                "type": None if adjustment is None else adjustment[0].value,
                "total": result.total,
                "threshold": payload.low_stock_threshold,
            },
        )
        return _row(row)

    async def history(self, variant_id: UUID, params: PageParams) -> Page[MovementRow]:
        async with self._session.begin():
            if not await self._repository.variant_exists(variant_id):
                raise _variant_not_found()
            rows, total = await self._repository.history(variant_id, params)
            items = [MovementRow.model_validate(row, from_attributes=True) for row in rows]
        return Page.build(items, total=total, params=params)

    async def reservations(
        self,
        *,
        status: ReservationStatus | None,
        order_id: UUID | None,
        variant_id: UUID | None,
        params: PageParams,
        now: datetime | None = None,
    ) -> Page[ReservationRow]:
        query = ReservationQuery(self._session)
        async with self._session.begin():
            rows, total = await query.page(
                status=status,
                order_id=order_id,
                variant_id=variant_id,
                params=params,
                now=now or utc_now(),
            )
            lines = await query.items([reservation.id for reservation, _ in rows])
        by_reservation: dict[UUID, list[ReservationItemRow]] = defaultdict(list)
        expired = {reservation.id for reservation, shown in rows if shown == EXPIRED}
        for line, sku in lines:
            line_status = line.status
            if line.reservation_id in expired and line_status == ReservationItemStatus.ACTIVE:
                # An expired reservation holds nothing, whatever the job has not swept yet.
                line_status = EXPIRED
            by_reservation[line.reservation_id].append(
                ReservationItemRow(
                    variant_id=line.variant_id, sku=sku, quantity=line.quantity, status=line_status
                )
            )
        items = [
            ReservationRow(
                id=reservation.id,
                order_id=reservation.order_id,
                user_id=reservation.user_id,
                status=shown,
                expires_at=reservation.expires_at,
                created_at=reservation.created_at,
                committed_at=reservation.committed_at,
                released_at=reservation.released_at,
                items=by_reservation[reservation.id],
            )
            for reservation, shown in rows
        ]
        return Page.build(items, total=total, params=params)
