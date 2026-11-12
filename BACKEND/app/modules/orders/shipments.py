"""Reading an order's shipment row, shared by the customer and admin views (ADM-02)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Shipment
from app.modules.orders.schemas import OrderShipmentResponse


async def shipment_of(session: AsyncSession, order_id: UUID) -> OrderShipmentResponse | None:
    """The order's shipment, once it started preparing."""
    shipment = await session.scalar(select(Shipment).where(Shipment.order_id == order_id))
    if shipment is None:
        return None
    return OrderShipmentResponse(
        tracking_code=shipment.tracking_code,
        shipped_at=shipment.shipped_at,
        delivered_at=shipment.delivered_at,
    )
