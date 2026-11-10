"""Static pages: public read and admin CRUD (CNT-04, PRD «درباره برند» ✓, D40).

Every write locks the row ``FOR UPDATE`` so each audit row's ``before`` is the previous
edit's ``after``. A soft-deleted page frees its slug.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final
from uuid import UUID

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, ErrorCode, NotFoundError
from app.core.time import utc_now
from app.db.models import PageStatus, StaticPage
from app.modules.auth.service import CurrentUser
from app.modules.content.schemas import (
    AdminPageResponse,
    CreatePageRequest,
    PublicPageResponse,
    UpdatePageRequest,
)
from app.shared.audit import record_audit
from app.shared.pagination import Page, PageParams, paginate

_ENTITY: Final = "static_page"
_AUDITED: Final = ("slug", "title", "body", "status")


@dataclass(frozen=True, slots=True)
class PageFilters:
    status: PageStatus | None = None


def _not_found() -> NotFoundError:
    # One answer for draft, deleted and unknown pages (no existence leak).
    return NotFoundError(message="Page not found")


def _snapshot(page: StaticPage) -> dict[str, Any]:
    return {field: getattr(page, field) for field in _AUDITED}


def _response(page: StaticPage) -> AdminPageResponse:
    return AdminPageResponse.model_validate(page)


class PageService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def public(self, slug: str) -> PublicPageResponse:
        statement = select(StaticPage).where(
            StaticPage.slug == slug,
            StaticPage.status == PageStatus.PUBLISHED,
            StaticPage.deleted_at.is_(None),
        )
        async with self._session.begin():
            page = (await self._session.scalars(statement)).one_or_none()
            if page is None:
                raise _not_found()
            return PublicPageResponse.model_validate(page)

    async def list_pages(self, filters: PageFilters, params: PageParams) -> Page[AdminPageResponse]:
        statement = select(StaticPage).where(StaticPage.deleted_at.is_(None))
        if filters.status is not None:
            statement = statement.where(StaticPage.status == filters.status)
        async with self._session.begin():
            rows, total = await paginate(
                self._session,
                statement,
                (StaticPage.slug.asc(),),
                tie_breaker=StaticPage.id,
                params=params,
            )
        return Page.build([_response(row[0]) for row in rows], total=total, params=params)

    async def create(
        self, actor: CurrentUser, payload: CreatePageRequest, request: Request
    ) -> AdminPageResponse:
        page = StaticPage(
            **payload.model_dump(),
            published_at=utc_now() if payload.status is PageStatus.PUBLISHED else None,
            created_by=actor.id,
            updated_by=actor.id,
        )
        async with self._session.begin():
            self._session.add(page)
            await self._flush()
            await record_audit(
                self._session,
                actor_id=actor.id,
                action="static_page.created",
                entity_type=_ENTITY,
                entity_id=page.id,
                before=None,
                after=_snapshot(page),
                request=request,
            )
            await self._session.refresh(page)
        return _response(page)

    async def update(
        self, actor: CurrentUser, page_id: UUID, payload: UpdatePageRequest, request: Request
    ) -> AdminPageResponse:
        sent = payload.model_dump(exclude_unset=True)
        async with self._session.begin():
            page = await self._live(page_id, lock=True)
            changed = {
                field: value for field, value in sent.items() if getattr(page, field) != value
            }
            if changed:
                before = {field: getattr(page, field) for field in changed}
                for field, value in changed.items():
                    setattr(page, field, value)
                if page.status == PageStatus.PUBLISHED and page.published_at is None:
                    page.published_at = utc_now()
                page.updated_by = actor.id
                await self._session.flush()
                await record_audit(
                    self._session,
                    actor_id=actor.id,
                    action="static_page.updated",
                    entity_type=_ENTITY,
                    entity_id=page.id,
                    before=before,
                    after=changed,
                    request=request,
                )
                await self._session.refresh(page)
        return _response(page)

    async def delete(self, actor: CurrentUser, page_id: UUID, request: Request) -> None:
        async with self._session.begin():
            page = await self._live(page_id, lock=True)
            page.soft_delete()
            page.updated_by = actor.id
            await self._session.flush()
            await record_audit(
                self._session,
                actor_id=actor.id,
                action="static_page.deleted",
                entity_type=_ENTITY,
                entity_id=page.id,
                before=_snapshot(page),
                after={"deleted": True},
                request=request,
            )

    async def _flush(self) -> None:
        try:
            await self._session.flush()
        except IntegrityError as exc:
            if "uq_static_pages_slug" in str(exc.orig):
                raise ConflictError(
                    code=ErrorCode.DUPLICATE_SLUG, message="Slug is already in use"
                ) from exc
            raise

    async def _live(self, page_id: UUID, *, lock: bool = False) -> StaticPage:
        statement = select(StaticPage).where(
            StaticPage.id == page_id, StaticPage.deleted_at.is_(None)
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        page = (await self._session.scalars(statement)).one_or_none()
        if page is None:
            raise _not_found()
        return page
