"""Admin banners: list, create, update, soft delete (CNT-03, PRD «محتوا و بنرها» ✓).

Images are Media (ADR-028) and never a product's own image. The link is internal only
(D41) and checked when saved: unknown or deleted → 404, not public → 422. The public read
(hero sections of ``GET /home``) checks again and hides a banner whose target stopped
being public. Every write locks the row and is audited.
"""

from __future__ import annotations

from typing import Any, Final
from uuid import UUID

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BadRequestError, NotFoundError
from app.db.models import Banner, TargetType
from app.modules.auth.service import CurrentUser
from app.modules.catalog.repository import CategoryRepository, media_storage_keys
from app.modules.content.references import ReferenceChecker
from app.modules.content.schemas import (
    AdminBannerResponse,
    CreateBannerRequest,
    UpdateBannerRequest,
)
from app.shared.audit import record_audit
from app.shared.pagination import Page, PageParams, paginate
from app.shared.storage import FileStorage

_ENTITY: Final = "banner"
_FIELDS: Final = (
    "title",
    "subtitle",
    "image_media_id",
    "mobile_image_media_id",
    "target_type",
    "target_id",
    "display_order",
    "is_active",
    "starts_at",
    "ends_at",
)


def _problem(where: str, message: str) -> dict[str, str]:
    return {"field": f"body.{where}", "message": message, "type": "value_error"}


def _check_shape(values: dict[str, Any]) -> None:
    problems: list[dict[str, str]] = []
    if (values["target_type"] == TargetType.NONE) != (values["target_id"] is None):
        problems.append(_problem("target_id", "Required unless target_type is none, then null"))
    starts, ends = values["starts_at"], values["ends_at"]
    if starts is not None and ends is not None and starts >= ends:
        problems.append(_problem("ends_at", "Must be after starts_at"))
    if problems:
        raise BadRequestError(message="Request validation failed", details=problems)


def _snapshot(banner: Banner) -> dict[str, Any]:
    return {name: getattr(banner, name) for name in _FIELDS}


class BannerService:
    def __init__(
        self, session: AsyncSession, categories: CategoryRepository, storage: FileStorage
    ) -> None:
        self._session = session
        self._categories = categories
        self._storage = storage

    async def _responses(self, banners: list[Banner]) -> list[AdminBannerResponse]:
        keys = await media_storage_keys(
            self._session,
            [banner.image_media_id for banner in banners]
            + [banner.mobile_image_media_id for banner in banners],
        )

        def url(media_id: UUID | None) -> str | None:
            key = None if media_id is None else keys.get(media_id)
            return None if key is None else self._storage.url(key)

        return [
            AdminBannerResponse(
                **{name: getattr(banner, name) for name in (*_FIELDS, "id")},
                image_url=url(banner.image_media_id),
                mobile_image_url=url(banner.mobile_image_media_id),
                created_at=banner.created_at,
                updated_at=banner.updated_at,
            )
            for banner in banners
        ]

    async def list_banners(self, params: PageParams) -> Page[AdminBannerResponse]:
        statement = select(Banner).where(Banner.deleted_at.is_(None))
        async with self._session.begin():
            rows, total = await paginate(
                self._session,
                statement,
                (Banner.display_order.asc(),),
                tie_breaker=Banner.id,
                params=params,
            )
            items = await self._responses([row[0] for row in rows])
        return Page.build(items, total=total, params=params)

    async def create(
        self, actor: CurrentUser, payload: CreateBannerRequest, request: Request
    ) -> AdminBannerResponse:
        values = payload.model_dump()
        _check_shape(values)
        async with self._session.begin():
            await self._check_references(values, set(values))
            banner = Banner(**values, created_by=actor.id, updated_by=actor.id)
            self._session.add(banner)
            await self._session.flush()
            await record_audit(
                self._session,
                actor_id=actor.id,
                action="banner.created",
                entity_type=_ENTITY,
                entity_id=banner.id,
                before=None,
                after=_snapshot(banner),
                request=request,
            )
            await self._session.refresh(banner)
            [response] = await self._responses([banner])
        return response

    async def update(
        self, actor: CurrentUser, banner_id: UUID, payload: UpdateBannerRequest, request: Request
    ) -> AdminBannerResponse:
        sent = payload.model_dump(exclude_unset=True)
        async with self._session.begin():
            banner = await self._live(banner_id)
            values = {name: sent.get(name, getattr(banner, name)) for name in _FIELDS}
            _check_shape(values)
            changed = {
                name: value for name, value in sent.items() if getattr(banner, name) != value
            }
            await self._check_references(values, set(changed))
            if changed:
                before = {name: getattr(banner, name) for name in changed}
                for name, value in changed.items():
                    setattr(banner, name, value)
                banner.updated_by = actor.id
                await self._session.flush()
                await record_audit(
                    self._session,
                    actor_id=actor.id,
                    action="banner.updated",
                    entity_type=_ENTITY,
                    entity_id=banner.id,
                    before=before,
                    after=changed,
                    request=request,
                )
                await self._session.refresh(banner)
            [response] = await self._responses([banner])
        return response

    async def delete(self, actor: CurrentUser, banner_id: UUID, request: Request) -> None:
        async with self._session.begin():
            banner = await self._live(banner_id)
            banner.soft_delete()
            banner.updated_by = actor.id
            await self._session.flush()
            await record_audit(
                self._session,
                actor_id=actor.id,
                action="banner.deleted",
                entity_type=_ENTITY,
                entity_id=banner.id,
                before=_snapshot(banner),
                after={"deleted": True},
                request=request,
            )

    async def _check_references(self, values: dict[str, Any], changed: set[str]) -> None:
        check = ReferenceChecker(self._session, self._categories)
        if {"target_type", "target_id"} & changed:
            await check.target(values["target_type"], values["target_id"])
        for name in ("image_media_id", "mobile_image_media_id"):
            if name in changed and values[name] is not None:
                await check.media(values[name])

    async def _live(self, banner_id: UUID) -> Banner:
        statement = (
            select(Banner)
            .where(Banner.id == banner_id, Banner.deleted_at.is_(None))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        banner = (await self._session.scalars(statement)).one_or_none()
        if banner is None:
            raise NotFoundError(message="Banner not found")
        return banner
