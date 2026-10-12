from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any, Final
from uuid import UUID

from sqlalchemy import UnaryExpression
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.core.errors import (
    BusinessRuleError,
    ConflictError,
    ErrorCode,
    ForbiddenError,
    NotFoundError,
)
from app.db.models import Category, CategoryFilter
from app.modules.auth.service import CurrentUser
from app.modules.catalog.admin_schemas import (
    CONTENT_FIELDS,
    AdminCategoryFilterResponse,
    AdminCategoryFiltersResponse,
    AdminCategoryResponse,
    CreateCategoryRequest,
    ReplaceCategoryFiltersRequest,
    UpdateCategoryRequest,
)
from app.modules.catalog.repository import (
    AdminCategoryRepository,
    is_product_media,
    media_storage_keys,
)
from app.shared.audit import record_audit
from app.shared.pagination import Page, PageParams
from app.shared.storage import FileStorage

logger = logging.getLogger("app.catalog")

# The PRD sets no limit; a root category has depth 1.
MAX_CATEGORY_DEPTH: Final = 5
MANAGE_PERMISSION: Final = "catalog:manage"
_AUDITED_FIELDS: Final = (
    "parent_id",
    "title",
    "slug",
    "description",
    "icon_key",
    "image_media_id",
    "display_order",
    "is_active",
    "seo_title",
    "seo_description",
)


def _not_found() -> NotFoundError:
    return NotFoundError(message="Category not found")


def _duplicate_slug() -> ConflictError:
    return ConflictError(code=ErrorCode.DUPLICATE_SLUG, message="Slug is already in use")


def _too_deep() -> BusinessRuleError:
    return BusinessRuleError(
        message=f"Categories may be nested at most {MAX_CATEGORY_DEPTH} levels deep"
    )


def _snapshot(category: Category) -> dict[str, Any]:
    return {field: getattr(category, field) for field in _AUDITED_FIELDS}


def _filters_snapshot(filters: Sequence[CategoryFilter]) -> list[dict[str, Any]]:
    fields = ("attribute_key", "label", "filter_type", "display_order", "is_active")
    snapshot = [{field: getattr(item, field) for field in fields} for item in filters]
    return sorted(snapshot, key=lambda item: str(item["attribute_key"]))


def _filters_response(filters: Sequence[CategoryFilter]) -> AdminCategoryFiltersResponse:
    return AdminCategoryFiltersResponse(
        items=[
            AdminCategoryFilterResponse.model_validate(item, from_attributes=True)
            for item in filters
        ]
    )


class AdminCategoryService:
    """Category administration; every write is audited in the same transaction (ADR-023)."""

    def __init__(
        self,
        session: AsyncSession,
        repository: AdminCategoryRepository,
        storage: FileStorage,
    ) -> None:
        self._session = session
        self._repository = repository
        self._storage = storage

    async def _responses(self, categories: Sequence[Category]) -> list[AdminCategoryResponse]:
        keys = await media_storage_keys(
            self._session, [category.image_media_id for category in categories]
        )
        return [
            AdminCategoryResponse.model_validate(
                {
                    **{
                        field: getattr(category, field)
                        for field in AdminCategoryResponse.model_fields
                        if field != "image_url"
                    },
                    "image_url": None
                    if category.image_media_id is None
                    else self._storage.url(keys[category.image_media_id]),
                }
            )
            for category in categories
        ]

    async def _response(self, category: Category) -> AdminCategoryResponse:
        return (await self._responses([category]))[0]

    async def _check_image(self, media_id: UUID | None) -> None:
        if media_id is None:
            return
        if not await media_storage_keys(self._session, [media_id]):
            raise BusinessRuleError(message="Image media not found")
        # A product image is deleted with its product media (CAT-11); sharing it would
        # block that delete through the categories FK.
        if await is_product_media(self._session, media_id):
            raise BusinessRuleError(message="Image media belongs to a product")

    async def list_categories(
        self, order_by: Sequence[UnaryExpression[Any]], paging: PageParams
    ) -> Page[AdminCategoryResponse]:
        async with self._session.begin():
            categories, total = await self._repository.list_page(
                order_by, offset=paging.offset, limit=paging.limit
            )
            items = await self._responses(categories)
        return Page.build(items, total=total, params=paging)

    async def create(
        self, actor: CurrentUser, payload: CreateCategoryRequest, audit_request: Request | None
    ) -> AdminCategoryResponse:
        async with self._session.begin():
            await self._repository.lock_tree()
            await self._check_image(payload.image_media_id)
            if payload.parent_id is not None:
                await self._check_parent(payload.parent_id, subtree_height=1)
            if await self._repository.slug_taken(payload.slug):
                raise _duplicate_slug()
            category = Category(**payload.model_dump())
            self._session.add(category)
            await self._flush()
            await record_audit(
                self._session,
                actor_id=actor.id,
                action="category.created",
                entity_type="category",
                entity_id=category.id,
                before=None,
                after=_snapshot(category),
                request=audit_request,
            )
            response = await self._response(category)
        logger.info("category.created", extra={"category_id": str(category.id)})
        return response

    async def update(
        self,
        actor: CurrentUser,
        category_id: UUID,
        payload: UpdateCategoryRequest,
        audit_request: Request | None,
    ) -> AdminCategoryResponse:
        fields = payload.model_fields_set
        # Checked on the fields sent, not the fields changed: sending a structural field
        # at all needs catalog:manage (ADR-023).
        if fields - CONTENT_FIELDS and MANAGE_PERMISSION not in actor.permissions:
            raise ForbiddenError(message="Changing category structure requires catalog:manage")
        async with self._session.begin():
            await self._repository.lock_tree()
            category = await self._repository.lock(category_id)
            if category is None:
                raise _not_found()
            changes = {
                field: getattr(payload, field)
                for field in sorted(fields)
                if getattr(payload, field) != getattr(category, field)
            }
            if not changes:
                return await self._response(category)
            if "image_media_id" in changes:
                await self._check_image(changes["image_media_id"])
            if "slug" in changes and await self._repository.slug_taken(
                changes["slug"], exclude_id=category.id
            ):
                raise _duplicate_slug()
            if "parent_id" in changes:
                await self._check_move(category.id, changes["parent_id"])

            before = _snapshot(category)
            for field, value in changes.items():
                setattr(category, field, value)
            await self._flush()
            await record_audit(
                self._session,
                actor_id=actor.id,
                action="category.updated",
                entity_type="category",
                entity_id=category.id,
                before=before,
                after=_snapshot(category),
                request=audit_request,
            )
            response = await self._response(category)
        logger.info(
            "category.updated",
            extra={"category_id": str(category.id), "fields": sorted(changes)},
        )
        return response

    async def delete(
        self, actor: CurrentUser, category_id: UUID, audit_request: Request | None
    ) -> None:
        """Soft delete; a category still holding sub-categories or products is a 409."""
        async with self._session.begin():
            await self._repository.lock_tree()
            category = await self._repository.lock(category_id)
            if category is None:
                raise _not_found()
            if await self._repository.has_children(category.id):
                raise ConflictError(message="Category still has sub-categories")
            if await self._repository.has_products(category.id):
                raise ConflictError(message="Category still has products")
            category.soft_delete()
            await self._session.flush()
            await record_audit(
                self._session,
                actor_id=actor.id,
                action="category.deleted",
                entity_type="category",
                entity_id=category.id,
                before=_snapshot(category),
                after=None,
                request=audit_request,
            )
        logger.info("category.deleted", extra={"category_id": str(category.id)})

    async def replace_filters(
        self,
        actor: CurrentUser,
        category_id: UUID,
        payload: ReplaceCategoryFiltersRequest,
        audit_request: Request | None,
    ) -> AdminCategoryFiltersResponse:
        """Replace the category's filter set; an identical set is a no-op without audit."""
        async with self._session.begin():
            await self._repository.lock_tree()
            category = await self._repository.lock(category_id)
            if category is None:
                raise _not_found()
            current = await self._repository.filters_of(category.id)
            before = _filters_snapshot(current)
            after = sorted(
                (item.model_dump(mode="json") for item in payload.filters),
                key=lambda item: item["attribute_key"],
            )
            if before == after:
                return _filters_response(current)

            filters = [
                CategoryFilter(category_id=category.id, **item.model_dump())
                for item in payload.filters
            ]
            await self._repository.replace_filters(category.id, filters)
            await record_audit(
                self._session,
                actor_id=actor.id,
                action="category.filters_updated",
                entity_type="category",
                entity_id=category.id,
                before={"filters": before},
                after={"filters": after},
                request=audit_request,
            )
            saved = await self._repository.filters_of(category.id)
        logger.info("category.filters_updated", extra={"category_id": str(category.id)})
        return _filters_response(saved)

    async def _check_parent(self, parent_id: UUID, *, subtree_height: int) -> None:
        """The parent must exist, and the moved subtree must fit under it."""
        if await self._repository.get(parent_id) is None:
            raise BusinessRuleError(message="Parent category not found")
        if await self._repository.depth(parent_id) + subtree_height > MAX_CATEGORY_DEPTH:
            raise _too_deep()

    async def _check_move(self, category_id: UUID, new_parent_id: UUID | None) -> None:
        descendants = await self._repository.descendants(category_id)
        subtree_height = 1 + max(descendants.values(), default=0)
        if new_parent_id is None:
            if subtree_height > MAX_CATEGORY_DEPTH:
                raise _too_deep()
            return
        if new_parent_id == category_id or new_parent_id in descendants:
            raise ConflictError(message="A category cannot be moved under itself")
        await self._check_parent(new_parent_id, subtree_height=subtree_height)

    async def _flush(self) -> None:
        # Backstop for the slug pre-check; the tree lock makes this practically unreachable.
        try:
            await self._session.flush()
        except IntegrityError as exc:
            if "uq_categories_slug" in str(exc.orig):
                raise _duplicate_slug() from exc
            raise
