"""FAQ: public grouped read and admin CRUD (CNT-05, PRD «سؤالات متداول» ✓, D40).

Every write locks the row ``FOR UPDATE`` so each audit row's ``before`` is the previous
edit's ``after``.
"""

from __future__ import annotations

from typing import Any, Final
from uuid import UUID

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.db.models import FaqItem
from app.modules.auth.service import CurrentUser
from app.modules.content.schemas import (
    AdminFaqResponse,
    CreateFaqRequest,
    PublicFaqGroup,
    PublicFaqItem,
    PublicFaqResponse,
    UpdateFaqRequest,
)
from app.shared.audit import record_audit
from app.shared.pagination import Page, PageParams, paginate

_ENTITY: Final = "faq_item"
_AUDITED: Final = ("group_title", "question", "answer", "display_order", "is_published")


def _not_found() -> NotFoundError:
    return NotFoundError(message="FAQ item not found")


def _snapshot(item: FaqItem) -> dict[str, Any]:
    return {field: getattr(item, field) for field in _AUDITED}


def _response(item: FaqItem) -> AdminFaqResponse:
    return AdminFaqResponse.model_validate(item)


class FaqService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def public(self) -> PublicFaqResponse:
        """Groups appear in the order of their first question."""
        statement = (
            select(FaqItem)
            .where(FaqItem.is_published.is_(True), FaqItem.deleted_at.is_(None))
            .order_by(FaqItem.display_order.asc(), FaqItem.id.asc())
        )
        async with self._session.begin():
            items = list(await self._session.scalars(statement))
        groups: dict[str, list[PublicFaqItem]] = {}
        for item in items:
            groups.setdefault(item.group_title, []).append(
                PublicFaqItem(id=item.id, question=item.question, answer=item.answer)
            )
        return PublicFaqResponse(
            groups=[PublicFaqGroup(title=title, items=rows) for title, rows in groups.items()]
        )

    async def list_items(self, params: PageParams) -> Page[AdminFaqResponse]:
        statement = select(FaqItem).where(FaqItem.deleted_at.is_(None))
        async with self._session.begin():
            rows, total = await paginate(
                self._session,
                statement,
                (FaqItem.display_order.asc(),),
                tie_breaker=FaqItem.id,
                params=params,
            )
        return Page.build([_response(row[0]) for row in rows], total=total, params=params)

    async def create(
        self, actor: CurrentUser, payload: CreateFaqRequest, request: Request
    ) -> AdminFaqResponse:
        item = FaqItem(**payload.model_dump(), created_by=actor.id, updated_by=actor.id)
        async with self._session.begin():
            self._session.add(item)
            await self._session.flush()
            await record_audit(
                self._session,
                actor_id=actor.id,
                action="faq_item.created",
                entity_type=_ENTITY,
                entity_id=item.id,
                before=None,
                after=_snapshot(item),
                request=request,
            )
            await self._session.refresh(item)
        return _response(item)

    async def update(
        self, actor: CurrentUser, item_id: UUID, payload: UpdateFaqRequest, request: Request
    ) -> AdminFaqResponse:
        sent = payload.model_dump(exclude_unset=True)
        async with self._session.begin():
            item = await self._live(item_id, lock=True)
            changed = {
                field: value for field, value in sent.items() if getattr(item, field) != value
            }
            if changed:
                before = {field: getattr(item, field) for field in changed}
                for field, value in changed.items():
                    setattr(item, field, value)
                item.updated_by = actor.id
                await self._session.flush()
                await record_audit(
                    self._session,
                    actor_id=actor.id,
                    action="faq_item.updated",
                    entity_type=_ENTITY,
                    entity_id=item.id,
                    before=before,
                    after=changed,
                    request=request,
                )
                await self._session.refresh(item)
        return _response(item)

    async def delete(self, actor: CurrentUser, item_id: UUID, request: Request) -> None:
        async with self._session.begin():
            item = await self._live(item_id, lock=True)
            item.soft_delete()
            item.updated_by = actor.id
            await self._session.flush()
            await record_audit(
                self._session,
                actor_id=actor.id,
                action="faq_item.deleted",
                entity_type=_ENTITY,
                entity_id=item.id,
                before=_snapshot(item),
                after={"deleted": True},
                request=request,
            )

    async def _live(self, item_id: UUID, *, lock: bool = False) -> FaqItem:
        statement = select(FaqItem).where(FaqItem.id == item_id, FaqItem.deleted_at.is_(None))
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        item = (await self._session.scalars(statement)).one_or_none()
        if item is None:
            raise _not_found()
        return item
