from __future__ import annotations

import logging
from collections.abc import Collection, Sequence
from typing import Any, Final
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import UnaryExpression
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.core.errors import (
    BadRequestError,
    BusinessRuleError,
    ConflictError,
    ErrorCode,
    ForbiddenError,
    NotFoundError,
)
from app.db.models import Category
from app.modules.auth.service import CurrentUser
from app.modules.catalog.admin_schemas import (
    CONTENT_FIELDS,
    AdminCategoryResponse,
    CreateCategoryRequest,
    UpdateCategoryRequest,
)
from app.modules.catalog.repository import AdminCategoryRepository
from app.shared.audit import record_audit
from app.shared.pagination import Page, PageParams

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
    "image_url",
    "display_order",
    "is_active",
    "seo_title",
    "seo_description",
)


def check_image_url(url: str, allowed_hosts: Collection[str]) -> None:
    """Accept only ``https://<allowed host>/...``; anything else is a 400 on ``image_url``.

    No user info, no explicit port and no control characters, so the stored URL cannot
    point anywhere but an allowed host (javascript:, http: and foreign hosts all fail).
    """
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise _invalid_image_url() from None
    valid = (
        url.isascii()
        and url.isprintable()
        and not any(char in url for char in " \\")
        and parts.scheme == "https"
        and port is None
        and parts.hostname is not None
        # Equal only without user info or port: "user@host" or "host:443" differ.
        and parts.netloc.lower() == parts.hostname
        and parts.hostname in allowed_hosts
    )
    if not valid:
        raise _invalid_image_url()


def _invalid_image_url() -> BadRequestError:
    return BadRequestError(
        message="Request validation failed",
        details=[
            {
                "field": "body.image_url",
                "message": "Must be an https URL on an allowed media host",
                "type": "value_error",
            }
        ],
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


def _response(category: Category) -> AdminCategoryResponse:
    return AdminCategoryResponse.model_validate(category, from_attributes=True)


class AdminCategoryService:
    """Category administration; every write is audited in the same transaction (ADR-023)."""

    def __init__(
        self,
        session: AsyncSession,
        repository: AdminCategoryRepository,
        allowed_media_hosts: Collection[str],
    ) -> None:
        self._session = session
        self._repository = repository
        self._allowed_media_hosts = frozenset(allowed_media_hosts)

    async def list_categories(
        self, order_by: Sequence[UnaryExpression[Any]], paging: PageParams
    ) -> Page[AdminCategoryResponse]:
        async with self._session.begin():
            categories, total = await self._repository.list_page(
                order_by, offset=paging.offset, limit=paging.limit
            )
        return Page.build([_response(item) for item in categories], total=total, params=paging)

    async def create(
        self, actor: CurrentUser, payload: CreateCategoryRequest, audit_request: Request | None
    ) -> AdminCategoryResponse:
        if payload.image_url is not None:
            check_image_url(payload.image_url, self._allowed_media_hosts)
        async with self._session.begin():
            await self._repository.lock_tree()
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
        logger.info("category.created", extra={"category_id": str(category.id)})
        return _response(category)

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
        if payload.image_url is not None:
            check_image_url(payload.image_url, self._allowed_media_hosts)
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
                return _response(category)
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
        logger.info(
            "category.updated",
            extra={"category_id": str(category.id), "fields": sorted(changes)},
        )
        return _response(category)

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
