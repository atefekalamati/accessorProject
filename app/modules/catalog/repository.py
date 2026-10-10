from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import UnaryExpression, exists, func, literal, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.db.models import Category, Product
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


# Recursive walks stop here even if corrupt data ever contained a cycle.
_MAX_WALK = 64


class AdminCategoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_tree(self) -> None:
        """Serialize category writes until the transaction ends.

        Two concurrent parent changes (A under B, B under A) are each valid alone; the
        lock makes the second one see the first, so the cycle check cannot be raced.
        """
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": "catalog:category_tree"},
        )

    async def list_page(
        self, order_by: Sequence[UnaryExpression[Any]], *, offset: int, limit: int
    ) -> tuple[list[Category], int]:
        total = await self._session.scalar(
            select(func.count()).select_from(Category).where(not_deleted(Category))
        )
        statement = (
            select(Category)
            .where(not_deleted(Category))
            .order_by(*order_by)
            .offset(offset)
            .limit(limit)
        )
        return list((await self._session.scalars(statement)).all()), total or 0

    async def get(self, category_id: UUID) -> Category | None:
        statement = select(Category).where(Category.id == category_id, not_deleted(Category))
        return (await self._session.scalars(statement)).one_or_none()

    async def lock(self, category_id: UUID) -> Category | None:
        statement = (
            select(Category)
            .where(Category.id == category_id, not_deleted(Category))
            .with_for_update()
        )
        return (await self._session.scalars(statement)).one_or_none()

    async def slug_taken(self, slug: str, *, exclude_id: UUID | None = None) -> bool:
        criteria = [Category.slug == slug, not_deleted(Category)]
        if exclude_id is not None:
            criteria.append(Category.id != exclude_id)
        return bool(await self._session.scalar(select(exists().where(*criteria))))

    async def depth(self, category_id: UUID) -> int:
        """Levels from the root down to ``category_id``, inclusive (a root has depth 1)."""
        chain = (
            select(Category.id, Category.parent_id, literal(1).label("level"))
            .where(Category.id == category_id)
            .cte("category_ancestors", recursive=True)
        )
        parent = aliased(Category)
        chain = chain.union_all(
            select(parent.id, parent.parent_id, chain.c.level + 1)
            .join(chain, parent.id == chain.c.parent_id)
            .where(chain.c.level < _MAX_WALK)
        )
        return int(await self._session.scalar(select(func.max(chain.c.level))) or 0)

    async def descendants(self, category_id: UUID) -> dict[UUID, int]:
        """Non-deleted descendants of ``category_id`` with their level below it (child = 1)."""
        tree = (
            select(Category.id, literal(1).label("level"))
            .where(Category.parent_id == category_id, not_deleted(Category))
            .cte("category_descendants", recursive=True)
        )
        child = aliased(Category)
        tree = tree.union_all(
            select(child.id, tree.c.level + 1)
            .join(tree, child.parent_id == tree.c.id)
            .where(child.deleted_at.is_(None), tree.c.level < _MAX_WALK)
        )
        rows = (await self._session.execute(select(tree.c.id, tree.c.level))).all()
        return {row.id: int(row.level) for row in rows}

    async def has_children(self, category_id: UUID) -> bool:
        criteria = (Category.parent_id == category_id, not_deleted(Category))
        return bool(await self._session.scalar(select(exists().where(*criteria))))

    async def has_products(self, category_id: UUID) -> bool:
        criteria = (Product.category_id == category_id, not_deleted(Product))
        return bool(await self._session.scalar(select(exists().where(*criteria))))
