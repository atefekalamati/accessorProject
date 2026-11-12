"""Admin home sections: list, create, update, soft delete (CNT-02, PRD «صفحه اصلی» ✓, D41).

A section is validated as a whole after every write (its type decides which items and
fields it may have; 400 otherwise). Everything it points at is checked when saved: unknown
or deleted → 404, not public (draft product, hidden category, unpublished page) → 422. The
public read checks again, since a target can stop being public later (CNT-01).

``display_order`` is unique among live sections (409). Every write locks the row and is
audited with the full section, items included. Sent ``items`` replace the current list;
their order is the list order.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Final
from uuid import UUID

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BadRequestError, ConflictError, NotFoundError
from app.db.models import (
    HomeSection,
    HomeSectionItem,
    ProductSource,
    SectionType,
    TargetType,
)
from app.modules.auth.service import CurrentUser
from app.modules.catalog.repository import CategoryRepository
from app.modules.content.references import ReferenceChecker
from app.modules.content.schemas import (
    AdminSectionItem,
    AdminSectionResponse,
    CreateSectionRequest,
    UpdateSectionRequest,
)
from app.shared.audit import record_audit
from app.shared.pagination import Page, PageParams, paginate

_ENTITY: Final = "home_section"
_SECTION_FIELDS: Final = (
    "type",
    "title",
    "subtitle",
    "layout_variant",
    "display_order",
    "is_active",
    "starts_at",
    "ends_at",
    "target_type",
    "target_id",
    "product_source",
    "source_category_id",
    "product_limit",
)
_ITEM_FIELDS: Final = (
    "product_id",
    "category_id",
    "title_override",
    "body",
    "image_media_id",
    "icon_key",
    "is_active",
)
_TEXT_TYPES: Final = frozenset({SectionType.BENEFITS, SectionType.EDITORIAL})


@dataclass(slots=True)
class _Spec:
    """A section's values after a write: checked as a whole before saving."""

    values: dict[str, Any]
    items: list[dict[str, Any]] = field(default_factory=list)


def _problem(where: str, message: str) -> dict[str, str]:
    return {"field": f"body.{where}", "message": message, "type": "value_error"}


def _check_shape(spec: _Spec) -> None:
    """Rules across fields; anything wrong is a 400 listing every problem."""
    values = spec.values
    kind = values["type"]
    problems: list[dict[str, str]] = []
    if (values["target_type"] == TargetType.NONE) != (values["target_id"] is None):
        problems.append(_problem("target_id", "Required unless target_type is none, then null"))
    carousel = kind == SectionType.PRODUCT_CAROUSEL
    if carousel != (values["product_source"] is not None):
        problems.append(_problem("product_source", "Required for product_carousel only"))
    if (values["product_source"] == ProductSource.CATEGORY) != (
        values["source_category_id"] is not None
    ):
        problems.append(
            _problem("source_category_id", "Required when product_source is category only")
        )
    starts, ends = values["starts_at"], values["ends_at"]
    if starts is not None and ends is not None and starts >= ends:
        problems.append(_problem("ends_at", "Must be after starts_at"))
    if kind == SectionType.HERO and spec.items:
        problems.append(_problem("items", "A hero section shows banners and has no items"))
    if carousel and len(spec.items) > values["product_limit"]:
        problems.append(_problem("items", "More products than product_limit"))
    for index, item in enumerate(spec.items):
        product, category = item.get("product_id"), item.get("category_id")
        if kind == SectionType.CATEGORY_GRID and (category is None or product is not None):
            problems.append(_problem(f"items.{index}", "Needs category_id only"))
        elif carousel and (product is None or category is not None):
            problems.append(_problem(f"items.{index}", "Needs product_id only"))
        elif kind in _TEXT_TYPES:
            if product is not None or category is not None:
                problems.append(_problem(f"items.{index}", "Takes no product or category"))
            if item.get("title_override") is None and item.get("body") is None:
                problems.append(_problem(f"items.{index}", "Needs title_override or body"))
    if problems:
        raise BadRequestError(message="Request validation failed", details=problems)


def _snapshot(section: HomeSection, items: Sequence[HomeSectionItem]) -> dict[str, Any]:
    snapshot = {name: getattr(section, name) for name in _SECTION_FIELDS}
    snapshot["items"] = [{name: getattr(item, name) for name in _ITEM_FIELDS} for item in items]
    return snapshot


def _response(section: HomeSection, items: Sequence[HomeSectionItem]) -> AdminSectionResponse:
    return AdminSectionResponse.model_validate(
        {
            **{
                name: getattr(section, name)
                for name in AdminSectionResponse.model_fields
                if name != "items"
            },
            "items": [AdminSectionItem.model_validate(item) for item in items],
        }
    )


def _not_found(message: str) -> NotFoundError:
    return NotFoundError(message=message)


class AdminHomeService:
    def __init__(self, session: AsyncSession, categories: CategoryRepository) -> None:
        self._session = session
        self._categories = categories

    async def list_sections(self, params: PageParams) -> Page[AdminSectionResponse]:
        statement = select(HomeSection).where(HomeSection.deleted_at.is_(None))
        async with self._session.begin():
            rows, total = await paginate(
                self._session,
                statement,
                (HomeSection.display_order.asc(),),
                tie_breaker=HomeSection.id,
                params=params,
            )
            sections = [row[0] for row in rows]
            items = await self._items_of([section.id for section in sections])
        return Page.build(
            [_response(section, items[section.id]) for section in sections],
            total=total,
            params=params,
        )

    async def create(
        self, actor: CurrentUser, payload: CreateSectionRequest, request: Request
    ) -> AdminSectionResponse:
        data = payload.model_dump()
        spec = _Spec(values={name: data[name] for name in _SECTION_FIELDS}, items=data["items"])
        _check_shape(spec)
        async with self._session.begin():
            await self._check_references(spec, target=True, source=True, items=True)
            section = HomeSection(**spec.values, created_by=actor.id, updated_by=actor.id)
            self._session.add(section)
            await self._flush()
            items = await self._replace_items(section, spec.items)
            await record_audit(
                self._session,
                actor_id=actor.id,
                action="home_section.created",
                entity_type=_ENTITY,
                entity_id=section.id,
                before=None,
                after=_snapshot(section, items),
                request=request,
            )
            await self._session.refresh(section)
        return _response(section, items)

    async def update(
        self,
        actor: CurrentUser,
        section_id: UUID,
        payload: UpdateSectionRequest,
        request: Request,
    ) -> AdminSectionResponse:
        sent = payload.model_dump(exclude_unset=True)
        async with self._session.begin():
            section = await self._live(section_id)
            current = (await self._items_of([section.id]))[section.id]
            before = _snapshot(section, current)
            values = {name: sent.get(name, getattr(section, name)) for name in _SECTION_FIELDS}
            new_items = sent.get("items")
            spec = _Spec(
                values=values,
                items=new_items
                if new_items is not None
                else [{name: getattr(item, name) for name in _ITEM_FIELDS} for item in current],
            )
            _check_shape(spec)
            await self._check_references(
                spec,
                target=bool({"target_type", "target_id"} & sent.keys()),
                source="source_category_id" in sent,
                items=new_items is not None,
            )
            for name in _SECTION_FIELDS:
                if name in sent:
                    setattr(section, name, sent[name])
            items = current
            if new_items is not None:
                items = await self._replace_items(section, new_items)
            after = _snapshot(section, items)
            if after != before:
                section.updated_by = actor.id
                await self._flush()
                changed = [name for name in after if after[name] != before[name]]
                await record_audit(
                    self._session,
                    actor_id=actor.id,
                    action="home_section.updated",
                    entity_type=_ENTITY,
                    entity_id=section.id,
                    before={name: before[name] for name in changed},
                    after={name: after[name] for name in changed},
                    request=request,
                )
                await self._session.refresh(section)
        return _response(section, items)

    async def delete(self, actor: CurrentUser, section_id: UUID, request: Request) -> None:
        async with self._session.begin():
            section = await self._live(section_id)
            items = (await self._items_of([section.id]))[section.id]
            section.soft_delete()
            section.updated_by = actor.id
            await self._session.flush()
            await record_audit(
                self._session,
                actor_id=actor.id,
                action="home_section.deleted",
                entity_type=_ENTITY,
                entity_id=section.id,
                before=_snapshot(section, items),
                after={"deleted": True},
                request=request,
            )

    # --- helpers -------------------------------------------------------------------------

    async def _flush(self) -> None:
        try:
            await self._session.flush()
        except IntegrityError as exc:
            if "uq_home_sections_display_order" in str(exc.orig):
                raise ConflictError(
                    message="Another section already has this display_order",
                    details=[_problem("display_order", "Already in use")],
                ) from exc
            raise

    async def _live(self, section_id: UUID) -> HomeSection:
        statement = (
            select(HomeSection)
            .where(HomeSection.id == section_id, HomeSection.deleted_at.is_(None))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        section = (await self._session.scalars(statement)).one_or_none()
        if section is None:
            raise _not_found("Home section not found")
        return section

    async def _items_of(self, section_ids: Sequence[UUID]) -> dict[UUID, list[HomeSectionItem]]:
        items: dict[UUID, list[HomeSectionItem]] = {section_id: [] for section_id in section_ids}
        if not section_ids:
            return items
        rows = await self._session.scalars(
            select(HomeSectionItem)
            .where(HomeSectionItem.section_id.in_(section_ids))
            .order_by(HomeSectionItem.display_order, HomeSectionItem.id)
        )
        for item in rows:
            items[item.section_id].append(item)
        return items

    async def _replace_items(
        self, section: HomeSection, values: Sequence[dict[str, Any]]
    ) -> list[HomeSectionItem]:
        for old in (await self._items_of([section.id]))[section.id]:
            await self._session.delete(old)
        await self._session.flush()
        items = [
            HomeSectionItem(
                section_id=section.id,
                display_order=index,
                **{name: item.get(name) for name in _ITEM_FIELDS if name != "is_active"},
                is_active=item.get("is_active", True),
            )
            for index, item in enumerate(values)
        ]
        self._session.add_all(items)
        await self._session.flush()
        return items

    async def _check_references(
        self, spec: _Spec, *, target: bool, source: bool, items: bool
    ) -> None:
        values = spec.values
        check = ReferenceChecker(self._session, self._categories)
        if target:
            await check.target(values["target_type"], values["target_id"])
        if source and values["source_category_id"] is not None:
            await check.category(values["source_category_id"])
        if not items:
            return
        for item in spec.items:
            if item.get("product_id") is not None:
                await check.product(item["product_id"])
            if item.get("category_id") is not None:
                await check.category(item["category_id"])
            if item.get("image_media_id") is not None:
                await check.media(item["image_media_id"])
