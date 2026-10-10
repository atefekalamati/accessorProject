from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.db.models import Category
from app.db.models.common import not_deleted


class CategoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_visible(self) -> Sequence[Category]:
        """Active, non-deleted categories whose ancestors are all active and non-deleted.

        One recursive query walks down from the visible roots, so a category under an
        inactive or deleted ancestor is never reached (ADR-022).
        """
        visible = (
            select(Category.id)
            .where(Category.parent_id.is_(None), Category.is_active.is_(True))
            .where(not_deleted(Category))
            .cte("visible_categories", recursive=True)
        )
        child = aliased(Category)
        visible = visible.union_all(
            select(child.id)
            .join(visible, child.parent_id == visible.c.id)
            .where(child.is_active.is_(True), child.deleted_at.is_(None))
        )
        statement = (
            select(Category)
            .where(Category.id.in_(select(visible.c.id)))
            .order_by(Category.display_order, Category.id)
        )
        return (await self._session.scalars(statement)).all()
