"""Checks of what home sections and banners point at, when they are saved (CNT-02, CNT-03).

Unknown or deleted → 404; exists but not public (draft product, hidden category,
unpublished page, a product's own image) → 422. Links are internal only (D41).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BusinessRuleError, NotFoundError
from app.db.models import (
    Category,
    Media,
    PageStatus,
    Product,
    ProductStatus,
    StaticPage,
    TargetType,
)
from app.modules.catalog.repository import CategoryRepository, is_product_media


class ReferenceChecker:
    def __init__(self, session: AsyncSession, categories: CategoryRepository) -> None:
        self._session = session
        self._categories = categories
        self._visible: set[UUID] | None = None

    async def category(self, category_id: UUID) -> None:
        exists = await self._session.scalar(
            select(Category.id).where(Category.id == category_id, Category.deleted_at.is_(None))
        )
        if exists is None:
            raise NotFoundError(message="Category not found")
        if self._visible is None:
            self._visible = {category.id for category in await self._categories.list_visible()}
        if category_id not in self._visible:
            raise BusinessRuleError(message="Category is not public")

    async def product(self, product_id: UUID) -> None:
        status = await self._session.scalar(
            select(Product.status).where(Product.id == product_id, Product.deleted_at.is_(None))
        )
        if status is None:
            raise NotFoundError(message="Product not found")
        if status != ProductStatus.PUBLISHED:
            raise BusinessRuleError(message="Product is not published")

    async def page(self, page_id: UUID) -> None:
        status = await self._session.scalar(
            select(StaticPage.status).where(
                StaticPage.id == page_id, StaticPage.deleted_at.is_(None)
            )
        )
        if status is None:
            raise NotFoundError(message="Page not found")
        if status != PageStatus.PUBLISHED:
            raise BusinessRuleError(message="Page is not published")

    async def target(self, target_type: str, target_id: UUID | None) -> None:
        if target_id is None:
            return
        if target_type == TargetType.PRODUCT:
            await self.product(target_id)
        elif target_type == TargetType.CATEGORY:
            await self.category(target_id)
        elif target_type == TargetType.PAGE:
            await self.page(target_id)

    async def media(self, media_id: UUID) -> None:
        found = await self._session.scalar(select(Media.id).where(Media.id == media_id))
        if found is None:
            raise NotFoundError(message="Image media not found")
        # A product image is deleted with its product media (CAT-11).
        if await is_product_media(self._session, media_id):
            raise BusinessRuleError(message="Image media belongs to a product")
