from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.db.models import Category, CategoryFilterType, VariantOptionKey
from app.modules.catalog.repository import CategoryRepository
from app.modules.catalog.schemas import (
    BreadcrumbItem,
    CategoryDetailResponse,
    CategoryFiltersResponse,
    CategorySummary,
    CategoryTreeNode,
    CategoryTreeResponse,
    FilterValue,
    PublicCategoryFilter,
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


def _visible_by_slug(categories: Sequence[Category], slug: str) -> Category:
    category = next((item for item in categories if item.slug == slug), None)
    if category is None:
        raise NotFoundError(message="Category not found")
    return category


_OPTION_KEYS = frozenset(VariantOptionKey)


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
        category = _visible_by_slug(categories, slug)

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

    async def filters(self, slug: str) -> CategoryFiltersResponse:
        """Active filters of a visible category, each with the values its published products
        actually have; a filter without values is left out.

        ``range`` (price) filters have no data until product prices exist (CAT-07).
        """
        async with self._session.begin():
            category = _visible_by_slug(await self._repository.list_visible(), slug)
            filters = [
                item
                for item in await self._repository.active_filters(category.id)
                if item.filter_type != CategoryFilterType.RANGE
            ]
            keys = {item.attribute_key for item in filters}
            counts = [
                *await self._repository.option_value_counts(category.id, keys & _OPTION_KEYS),
                *await self._repository.attribute_value_counts(category.id, keys - _OPTION_KEYS),
            ]
        values: dict[str, list[FilterValue]] = defaultdict(list)
        for key, value, count in counts:
            values[key].append(FilterValue(value=value, count=count))
        return CategoryFiltersResponse(
            items=[
                PublicCategoryFilter(
                    key=item.attribute_key,
                    label=item.label,
                    type=item.filter_type,
                    values=values[item.attribute_key],
                )
                for item in filters
                if values.get(item.attribute_key)
            ]
        )
