"""The public home page: ``GET /home`` (CNT-01, PRD «صفحه اصلی» ✓, D36, D41, D42).

One response holds every active section in ``display_order``. Products appear as the
listing card (fresh price and stock); anything not public any more (SD rule) is left out:
a draft, archived or deleted product, a hidden category, an unpublished page. A section
left without items, or whose link target is not public, is not shown. One failing section
is logged and skipped, never failing the page. With no section to show, a default layout
(the main categories and the newest products) is returned instead.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now
from app.db.models import (
    Banner,
    Category,
    HomeSection,
    HomeSectionItem,
    PageStatus,
    Product,
    ProductSource,
    ProductStatus,
    SectionType,
    StaticPage,
    TargetType,
)
from app.db.models.common import not_deleted
from app.modules.catalog.product_query import ProductSort
from app.modules.catalog.product_service import ProductService
from app.modules.catalog.repository import CategoryRepository, media_storage_keys
from app.modules.catalog.schemas import CategorySummary, ProductCard
from app.modules.content.schemas import HomeItem, HomeResponse, HomeSectionOut, HomeTarget
from app.shared.storage import FileStorage

logger = logging.getLogger("app.content")

DEFAULT_LIMIT: Final = 12
DEFAULT_HERO_TITLE: Final = "ویترین"
DEFAULT_CATEGORIES_TITLE: Final = "دسته‌بندی‌ها"
DEFAULT_NEWEST_TITLE: Final = "جدیدترین‌ها"

_SOURCE_SORT: Final[Mapping[str, ProductSort]] = {
    ProductSource.NEWEST: ProductSort.NEWEST,
    ProductSource.BEST_SELLING: ProductSort.BEST_SELLING,
    ProductSource.DISCOUNT: ProductSort.DISCOUNT_DESC,
    ProductSource.CATEGORY: ProductSort.NEWEST,
}


@dataclass(frozen=True, slots=True)
class _Snapshot:
    """Everything read in the first transaction; sections are rendered from it."""

    sections: list[HomeSection]
    items: dict[UUID, list[HomeSectionItem]]
    categories: dict[UUID, Category]
    media_urls: dict[UUID, str]
    product_slugs: dict[UUID, str]
    page_slugs: dict[UUID, str]
    banners: list[Banner]


def active_window(model: Any, now: datetime) -> list[ColumnElement[bool]]:
    """Live, active and inside ``[starts_at, ends_at)`` at ``now`` (sections and banners)."""
    return [
        not_deleted(model),
        model.is_active.is_(True),
        or_(model.starts_at.is_(None), model.starts_at <= now),
        or_(model.ends_at.is_(None), now < model.ends_at),
    ]


class HomeService:
    def __init__(
        self,
        session: AsyncSession,
        products: ProductService,
        categories: CategoryRepository,
        storage: FileStorage,
    ) -> None:
        self._session = session
        self._products = products
        self._categories = categories
        self._storage = storage

    async def home(self, *, at: datetime | None = None) -> HomeResponse:
        now = at or utc_now()
        snapshot = await self._read(now)
        sections: list[HomeSectionOut] = []
        for section in snapshot.sections:
            try:
                rendered = await self._render(section, snapshot, now)
            except Exception:
                logger.exception("home.section_failed", extra={"section_id": str(section.id)})
                continue
            if rendered is not None:
                sections.append(rendered)
        if not sections:
            sections = await self._default_layout(snapshot, now)
        return HomeResponse(sections=sections, generated_at=now)

    async def _read(self, now: datetime) -> _Snapshot:
        async with self._session.begin():
            sections = list(
                await self._session.scalars(
                    select(HomeSection)
                    .where(*active_window(HomeSection, now))
                    .order_by(HomeSection.display_order, HomeSection.id)
                )
            )
            items: dict[UUID, list[HomeSectionItem]] = {section.id: [] for section in sections}
            if sections:
                rows = await self._session.scalars(
                    select(HomeSectionItem)
                    .where(
                        HomeSectionItem.section_id.in_(list(items)),
                        HomeSectionItem.is_active.is_(True),
                    )
                    .order_by(HomeSectionItem.display_order, HomeSectionItem.id)
                )
                for item in rows:
                    items[item.section_id].append(item)
            banners = list(
                await self._session.scalars(
                    select(Banner)
                    .where(*active_window(Banner, now))
                    .order_by(Banner.display_order, Banner.id)
                )
            )
            categories = {
                category.id: category for category in await self._categories.list_visible()
            }
            media_ids = [item.image_media_id for rows in items.values() for item in rows]
            media_ids += [category.image_media_id for category in categories.values()]
            media_ids += [banner.image_media_id for banner in banners]
            media_ids += [banner.mobile_image_media_id for banner in banners]
            linked: list[HomeSection | Banner] = [*sections, *banners]
            keys = await media_storage_keys(self._session, media_ids)
            product_slugs = await self._published_products(
                [row.target_id for row in linked if row.target_type == TargetType.PRODUCT]
            )
            page_slugs = await self._published_pages(
                [row.target_id for row in linked if row.target_type == TargetType.PAGE]
            )
        return _Snapshot(
            sections=sections,
            items=items,
            categories=categories,
            media_urls={media_id: self._storage.url(key) for media_id, key in keys.items()},
            product_slugs=product_slugs,
            page_slugs=page_slugs,
            banners=banners,
        )

    async def _published_products(self, ids: Sequence[UUID | None]) -> dict[UUID, str]:
        wanted = [item for item in ids if item is not None]
        if not wanted:
            return {}
        rows = await self._session.execute(
            select(Product.id, Product.slug).where(
                Product.id.in_(wanted),
                Product.status == ProductStatus.PUBLISHED,
                not_deleted(Product),
            )
        )
        return {row.id: row.slug for row in rows}

    async def _published_pages(self, ids: Sequence[UUID | None]) -> dict[UUID, str]:
        wanted = [item for item in ids if item is not None]
        if not wanted:
            return {}
        rows = await self._session.execute(
            select(StaticPage.id, StaticPage.slug).where(
                StaticPage.id.in_(wanted),
                StaticPage.status == PageStatus.PUBLISHED,
                not_deleted(StaticPage),
            )
        )
        return {row.id: row.slug for row in rows}

    def _target(
        self, row: HomeSection | Banner, snapshot: _Snapshot
    ) -> tuple[bool, HomeTarget | None]:
        """``(public, target)``; a section or banner whose target is not public is hidden."""
        if row.target_type == TargetType.NONE or row.target_id is None:
            return True, None
        slug: str | None = None
        if row.target_type == TargetType.PRODUCT:
            slug = snapshot.product_slugs.get(row.target_id)
        elif row.target_type == TargetType.CATEGORY:
            category = snapshot.categories.get(row.target_id)
            slug = None if category is None else category.slug
        elif row.target_type == TargetType.PAGE:
            slug = snapshot.page_slugs.get(row.target_id)
        if slug is None:
            return False, None
        return True, HomeTarget(type=row.target_type, slug=slug)

    def _banner_items(self, snapshot: _Snapshot) -> list[HomeItem]:
        items: list[HomeItem] = []
        for banner in snapshot.banners:
            public, target = self._target(banner, snapshot)
            image = self._image(banner.image_media_id, snapshot)
            if not public or image is None:
                continue
            items.append(
                HomeItem(
                    title=banner.title,
                    subtitle=banner.subtitle,
                    image_url=image,
                    mobile_image_url=self._image(banner.mobile_image_media_id, snapshot),
                    target=target,
                )
            )
        return items

    async def _render(
        self, section: HomeSection, snapshot: _Snapshot, now: datetime
    ) -> HomeSectionOut | None:
        public, target = self._target(section, snapshot)
        if not public:
            return None
        rows = snapshot.items[section.id]
        items: list[HomeItem]
        if section.type == SectionType.CATEGORY_GRID:
            items = self._category_items(rows, snapshot)
        elif section.type == SectionType.PRODUCT_CAROUSEL:
            items = await self._carousel(section, rows, snapshot, now)
        elif section.type in (SectionType.BENEFITS, SectionType.EDITORIAL):
            items = [self._text_item(item, snapshot) for item in rows]
        else:  # hero: the banners
            items = self._banner_items(snapshot)
        if not items:
            return None
        return HomeSectionOut(
            id=section.id,
            type=section.type,
            title=section.title,
            subtitle=section.subtitle,
            layout_variant=section.layout_variant,
            target=target,
            items=items,
        )

    def _image(self, media_id: UUID | None, snapshot: _Snapshot) -> str | None:
        return None if media_id is None else snapshot.media_urls.get(media_id)

    def _summary(self, category: Category, snapshot: _Snapshot) -> CategorySummary:
        return CategorySummary(
            id=category.id,
            title=category.title,
            slug=category.slug,
            icon_key=category.icon_key,
            image_url=self._image(category.image_media_id, snapshot),
        )

    def _text_item(self, item: HomeSectionItem, snapshot: _Snapshot) -> HomeItem:
        return HomeItem(
            title=item.title_override,
            body=item.body,
            icon_key=item.icon_key,
            image_url=self._image(item.image_media_id, snapshot),
        )

    def _category_items(
        self, rows: Sequence[HomeSectionItem], snapshot: _Snapshot
    ) -> list[HomeItem]:
        items: list[HomeItem] = []
        for item in rows:
            category = (
                None if item.category_id is None else snapshot.categories.get(item.category_id)
            )
            if category is None:  # hidden, deleted or not a category item
                continue
            summary = self._summary(category, snapshot)
            items.append(
                HomeItem(
                    title=item.title_override or category.title,
                    icon_key=item.icon_key or category.icon_key,
                    image_url=self._image(item.image_media_id, snapshot) or summary.image_url,
                    category=summary,
                )
            )
        return items

    async def _carousel(
        self,
        section: HomeSection,
        rows: Sequence[HomeSectionItem],
        snapshot: _Snapshot,
        now: datetime,
    ) -> list[HomeItem]:
        """Hand-picked products first (PRD: manual wins), then the source fills the rest."""
        limit = section.product_limit
        picked = [item for item in rows if item.product_id is not None]
        cards: list[ProductCard] = []
        titles: dict[UUID, str | None] = {}
        if picked:
            ids = [item.product_id for item in picked if item.product_id is not None]
            found = await self._products.cards(
                sort=ProductSort.NEWEST, limit=len(ids), at=now, product_ids=frozenset(ids)
            )
            by_id = {card.id: card for card in found}
            for item in picked:
                card = by_id.get(item.product_id) if item.product_id is not None else None
                if card is not None and card.id not in titles:
                    cards.append(card)
                    titles[card.id] = item.title_override
            cards = cards[:limit]
        sort = _SOURCE_SORT.get(section.product_source or ProductSource.MANUAL)
        if sort is not None and len(cards) < limit:
            category_id = None
            if section.product_source == ProductSource.CATEGORY:
                category_id = section.source_category_id
                if category_id is None or category_id not in snapshot.categories:
                    category_id = None
                    sort = None
            if sort is not None:
                extra = await self._products.cards(
                    sort=sort,
                    limit=limit,
                    at=now,
                    category_id=category_id,
                    has_discount=section.product_source == ProductSource.DISCOUNT,
                )
                for card in extra:
                    if len(cards) == limit:
                        break
                    if card.id not in titles:
                        cards.append(card)
                        titles[card.id] = None
        return [HomeItem(title=titles[card.id], product=card) for card in cards]

    async def _default_layout(self, snapshot: _Snapshot, now: datetime) -> list[HomeSectionOut]:
        """Banners, the main categories and the newest products, each when it has items."""
        sections: list[HomeSectionOut] = []
        banners = self._banner_items(snapshot)
        if banners:
            sections.append(
                HomeSectionOut(
                    id=None,
                    type=SectionType.HERO,
                    title=DEFAULT_HERO_TITLE,
                    subtitle=None,
                    layout_variant=None,
                    target=None,
                    items=banners,
                )
            )
        roots = [c for c in snapshot.categories.values() if c.parent_id is None][:DEFAULT_LIMIT]
        if roots:
            sections.append(
                HomeSectionOut(
                    id=None,
                    type=SectionType.CATEGORY_GRID,
                    title=DEFAULT_CATEGORIES_TITLE,
                    subtitle=None,
                    layout_variant=None,
                    target=None,
                    items=[
                        HomeItem(
                            title=category.title,
                            icon_key=category.icon_key,
                            image_url=self._image(category.image_media_id, snapshot),
                            category=self._summary(category, snapshot),
                        )
                        for category in roots
                    ],
                )
            )
        try:
            newest = await self._products.cards(
                sort=ProductSort.NEWEST, limit=DEFAULT_LIMIT, at=now
            )
        except Exception:
            logger.exception("home.default_products_failed")
            newest = []
        if newest:
            sections.append(
                HomeSectionOut(
                    id=None,
                    type=SectionType.PRODUCT_CAROUSEL,
                    title=DEFAULT_NEWEST_TITLE,
                    subtitle=None,
                    layout_variant=None,
                    target=None,
                    items=[HomeItem(product=card) for card in newest],
                )
            )
        return sections
