from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.db.models import Category
from app.modules.catalog.repository import CategoryRepository
from app.modules.catalog.schemas import (
    BreadcrumbItem,
    CategoryDetailResponse,
    CategorySummary,
    CategoryTreeNode,
    CategoryTreeResponse,
)


def _summary(category: Category) -> CategorySummary:
    return CategorySummary(
        id=category.id,
        title=category.title,
        slug=category.slug,
        icon_key=category.icon_key,
        image_url=category.image_url,
    )


def _children_by_parent(categories: Sequence[Category]) -> dict[UUID | None, list[Category]]:
    # The input is ordered by (display_order, id) and grouping keeps that order.
    children: dict[UUID | None, list[Category]] = defaultdict(list)
    for category in categories:
        children[category.parent_id].append(category)
    return children


class CategoryService:
    """Public category reads; hidden categories do not exist for these endpoints (ADR-022)."""

    def __init__(self, session: AsyncSession, repository: CategoryRepository) -> None:
        self._session = session
        self._repository = repository

    async def tree(self) -> CategoryTreeResponse:
        async with self._session.begin():
            categories = await self._repository.list_visible()
        children = _children_by_parent(categories)

        def build(category: Category) -> CategoryTreeNode:
            return CategoryTreeNode(
                **_summary(category).model_dump(),
                children=[build(child) for child in children.get(category.id, [])],
            )

        return CategoryTreeResponse(items=[build(root) for root in children.get(None, [])])

    async def detail(self, slug: str) -> CategoryDetailResponse:
        async with self._session.begin():
            categories = await self._repository.list_visible()
        category = next((item for item in categories if item.slug == slug), None)
        if category is None:
            raise NotFoundError(message="Category not found")

        by_id = {item.id: item for item in categories}
        path: list[Category] = []
        current: Category | None = category
        while current is not None:
            path.append(current)
            current = None if current.parent_id is None else by_id.get(current.parent_id)
        children = _children_by_parent(categories).get(category.id, [])
        return CategoryDetailResponse(
            id=category.id,
            title=category.title,
            slug=category.slug,
            description=category.description,
            icon_key=category.icon_key,
            image_url=category.image_url,
            seo_title=category.seo_title,
            seo_description=category.seo_description,
            breadcrumb=[
                BreadcrumbItem(id=item.id, title=item.title, slug=item.slug)
                for item in reversed(path)
            ],
            children=[_summary(child) for child in children],
        )
