from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import InventoryItem, ProductVariant
from app.db.models.common import not_deleted
from app.db.models.inventory import DEFAULT_WAREHOUSE_ID


class InventoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def variant_product_id(self, variant_id: UUID) -> UUID | None:
        """Product of a non-deleted variant, read ``FOR SHARE``.

        The share lock conflicts with a concurrent soft delete (CAT-11 updates the row), so
        stock never changes on a variant being deleted. Lock order for every stock write:
        variant (SHARE) → inventory_item (UPDATE); the Product row is not locked (ADR-034).
        """
        statement = (
            select(ProductVariant.product_id)
            .where(ProductVariant.id == variant_id, not_deleted(ProductVariant))
            .with_for_update(read=True)
        )
        return (await self._session.scalars(statement)).one_or_none()

    async def lock_default_item(self, variant_id: UUID, product_id: UUID) -> InventoryItem:
        """The variant's item in the default warehouse, created if missing, under FOR UPDATE.

        ``ON CONFLICT DO NOTHING`` makes concurrent first adjustments create one row; the
        lock then serializes them (ADR-029).

        Only manual adjustment may create an item. Reservation flows (INV-04..06) lock
        existing items only and treat a missing one as out of stock (ADR-034).
        """
        await self._session.execute(
            insert(InventoryItem)
            .values(
                warehouse_id=DEFAULT_WAREHOUSE_ID,
                product_id=product_id,
                variant_id=variant_id,
            )
            .on_conflict_do_nothing(index_elements=["variant_id", "warehouse_id"])
        )
        statement = (
            select(InventoryItem)
            .where(
                InventoryItem.variant_id == variant_id,
                InventoryItem.warehouse_id == DEFAULT_WAREHOUSE_ID,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return (await self._session.scalars(statement)).one()
