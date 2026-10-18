"""Shipping method reads shared by the public list and checkout (ADDR-02, ADR-045)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import ColumnElement, and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BusinessRuleError
from app.db.models import ShippingMethod


def selectable() -> ColumnElement[bool]:
    """A method a shopper may pick: active and not deleted."""
    return and_(ShippingMethod.is_active.is_(True), ShippingMethod.deleted_at.is_(None))


def shipping_unavailable() -> BusinessRuleError:
    """One answer for an unknown, deleted or inactive method (ORD-03/ORD-04: 422)."""
    return BusinessRuleError(
        message="This shipping method is not available",
        details=[{"field": "shipping_method_id", "type": "shipping_method_unavailable"}],
    )


class ShippingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_selectable(self) -> list[ShippingMethod]:
        statement = (
            select(ShippingMethod)
            .where(selectable())
            .order_by(ShippingMethod.display_order, ShippingMethod.title, ShippingMethod.id)
        )
        return list(await self._session.scalars(statement))

    async def get_selectable(self, method_id: UUID) -> ShippingMethod:
        """The method for checkout, or the 422 every unusable id gets."""
        statement = select(ShippingMethod).where(ShippingMethod.id == method_id, selectable())
        method = (await self._session.scalars(statement)).one_or_none()
        if method is None:
            raise shipping_unavailable()
        return method
