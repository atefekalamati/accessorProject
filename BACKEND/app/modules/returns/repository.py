"""Queries for return requests (ORD-08)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Order,
    OrderItem,
    ReturnItem,
    ReturnRequest,
    ReturnStatusHistory,
    Shipment,
)
from app.db.models.returns import RELEASED_STATUSES


class ReturnRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def owned_order_id(self, user_id: UUID, order_number: str) -> UUID | None:
        return await self._session.scalar(
            select(Order.id).where(Order.order_number == order_number, Order.user_id == user_id)
        )

    async def delivered_at(self, order_id: UUID) -> datetime | None:
        return await self._session.scalar(
            select(Shipment.delivered_at).where(Shipment.order_id == order_id)
        )

    async def order_items(self, order_id: UUID) -> list[OrderItem]:
        return list(
            await self._session.scalars(
                select(OrderItem).where(OrderItem.order_id == order_id).order_by(OrderItem.position)
            )
        )

    async def claimed(self, order_id: UUID) -> dict[UUID, int]:
        """Quantity per order line held by requests that were not rejected or cancelled."""
        rows = await self._session.execute(
            select(ReturnItem.order_item_id, func.sum(ReturnItem.quantity))
            .join(ReturnRequest, ReturnRequest.id == ReturnItem.return_request_id)
            .where(
                ReturnRequest.order_id == order_id,
                ReturnRequest.status.not_in([s.value for s in RELEASED_STATUSES]),
            )
            .group_by(ReturnItem.order_item_id)
        )
        return {item_id: int(total) for item_id, total in rows}

    async def owned_request(
        self, user_id: UUID, return_id: UUID, *, lock: bool = False
    ) -> ReturnRequest | None:
        statement = select(ReturnRequest).where(
            ReturnRequest.id == return_id, ReturnRequest.user_id == user_id
        )
        if lock:
            statement = statement.with_for_update()
        return await self._session.scalar(statement.execution_options(populate_existing=True))

    async def items_with_lines(self, return_id: UUID) -> list[tuple[ReturnItem, OrderItem]]:
        rows = await self._session.execute(
            select(ReturnItem, OrderItem)
            .join(OrderItem, OrderItem.id == ReturnItem.order_item_id)
            .where(ReturnItem.return_request_id == return_id)
            .order_by(OrderItem.position)
        )
        return [(row[0], row[1]) for row in rows]

    async def history(self, return_id: UUID) -> list[ReturnStatusHistory]:
        return list(
            await self._session.scalars(
                select(ReturnStatusHistory)
                .where(ReturnStatusHistory.return_request_id == return_id)
                .order_by(ReturnStatusHistory.created_at, ReturnStatusHistory.id)
            )
        )

    async def order_number(self, order_id: UUID) -> str:
        number = await self._session.scalar(select(Order.order_number).where(Order.id == order_id))
        if number is None:  # RESTRICT: a request's order cannot disappear
            raise RuntimeError("return request without its order")
        return number
