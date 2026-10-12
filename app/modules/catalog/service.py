from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.time import utc_now
from app.db.models import Category, CategoryFilterType, VariantOptionKey
from app.modules.catalog.repository import CategoryRepository, media_storage_keys
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
from app.shared.storage import FileStorage


def _summary(category: Category, image_url: str | None) -> CategorySummary:
    return CategorySummary(
        id=category.id,
        title=category.title,
        slug=category.slug,
        icon_key=category.icon_key,
        image_url=image_url,
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

    def __init__(
        self, session: AsyncSession, repository: CategoryRepository, storage: FileStorage
    ) -> None:
        self._session = session
        self._repository = repository
        self._storage = storage

    async def _image_urls(self, categories: Sequence[Category]) -> dict[UUID, str]:
        keys = await media_storage_keys(
            self._session, [category.image_media_id for category in categories]
        )
        return {media_id: self._storage.url(key) for media_id, key in keys.items()}

    @staticmethod
    def _url(category: Category, urls: dict[UUID, str]) -> str | None:
        return None if category.image_media_id is None else urls.get(category.image_media_id)

    async def tree(self) -> CategoryTreeResponse:
        async with self._session.begin():
            categories = await self._repository.list_visible()
            urls = await self._image_urls(categories)
        children = _children_by_parent(categories)

        def build(category: Category) -> CategoryTreeNode:
            return CategoryTreeNode(
                **_summary(category, self._url(category, urls)).model_dump(),
                children=[build(child) for child in children.get(category.id, [])],
            )

        return CategoryTreeResponse(items=[build(root) for root in children.get(None, [])])

    async def detail(self, slug: str) -> CategoryDetailResponse:
        async with self._session.begin():
            categories = await self._repository.list_visible()
            category = _visible_by_slug(categories, slug)
            children = _children_by_parent(categories).get(category.id, [])
            urls = await self._image_urls([category, *children])

        by_id = {item.id: item for item in categories}
        path: list[Category] = []
        current: Category | None = category
        while current is not None:
            path.append(current)
            current = None if current.parent_id is None else by_id.get(current.parent_id)
        return CategoryDetailResponse(
            id=category.id,
            title=category.title,
            slug=category.slug,
            description=category.description,
            icon_key=category.icon_key,
            image_url=self._url(category, urls),
            seo_title=category.seo_title,
            seo_description=category.seo_description,
            breadcrumb=[
                BreadcrumbItem(id=item.id, title=item.title, slug=item.slug)
                for item in reversed(path)
            ],
            children=[_summary(child, self._url(child, urls)) for child in children],
        )

    async def filters(self, slug: str, *, at: datetime | None = None) -> CategoryFiltersResponse:
        """Active filters of a visible category, each with the values its published products
        actually have; a filter without values is left out.

        The ``range`` filter (only ``price``, ADR-026) has the lowest and highest listing
        price instead: the price ``GET /categories/{slug}/products`` filters on (CAT-07).
        """
        now = at or utc_now()
        async with self._session.begin():
            category = _visible_by_slug(await self._repository.list_visible(), slug)
            filters = await self._repository.active_filters(category.id)
            keys = {
                item.attribute_key
                for item in filters
                if item.filter_type != CategoryFilterType.RANGE
            }
            counts = [
                *await self._repository.option_value_counts(category.id, keys & _OPTION_KEYS),
                *await self._repository.attribute_value_counts(category.id, keys - _OPTION_KEYS),
            ]
            has_range = any(item.filter_type == CategoryFilterType.RANGE for item in filters)
            bounds = await self._repository.price_bounds(category.id, now) if has_range else None
        values: dict[str, list[FilterValue]] = defaultdict(list)
        for key, value, count in counts:
            values[key].append(FilterValue(value=value, count=count))
        items: list[PublicCategoryFilter] = []
        for item in filters:
            if item.filter_type == CategoryFilterType.RANGE:
                if bounds is not None:
                    items.append(
                        PublicCategoryFilter(
                            key=item.attribute_key,
                            label=item.label,
                            type=item.filter_type,
                            values=[],
                            min=bounds[0],
                            max=bounds[1],
                        )
                    )
            elif values.get(item.attribute_key):
                items.append(
                    PublicCategoryFilter(
                        key=item.attribute_key,
                        label=item.label,
                        type=item.filter_type,
                        values=values[item.attribute_key],
                    )
                )
        return CategoryFiltersResponse(items=items)
