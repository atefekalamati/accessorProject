"""Contact form and its admin queue (CNT-06, PRD «تماس با ما» ✓, ADR-016, ADR-053).

Submissions are limited per client IP and per mobile over a rolling window. Advisory locks
on both keys make the caps exact under concurrent requests; they are taken in sorted order
so two requests cannot deadlock. Behind a reverse proxy the IP cap needs OPS-04.

A message holds personal data: it is shown only with ``contact_messages:manage``, never
logged, and its text never reaches the audit log.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Final
from uuid import UUID

from fastapi import Request
from sqlalchemy import ColumnElement, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import BusinessRuleError, ErrorCode, NotFoundError, RateLimitedError
from app.core.time import utc_now
from app.db.models import ContactMessage, ContactStatus
from app.modules.auth.service import CurrentUser
from app.modules.content.schemas import (
    AdminContactDetail,
    AdminContactSummary,
    ContactRequest,
    UpdateContactRequest,
)
from app.shared.audit import record_audit
from app.shared.pagination import Page, PageParams, paginate

_ENTITY: Final = "contact_message"
_TRANSITIONS: Final[Mapping[str, frozenset[str]]] = {
    ContactStatus.NEW: frozenset({ContactStatus.IN_PROGRESS}),
    ContactStatus.IN_PROGRESS: frozenset({ContactStatus.CLOSED}),
    ContactStatus.CLOSED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class ContactFilters:
    status: ContactStatus | None = None


class ContactService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    async def submit(
        self, payload: ContactRequest, *, user_id: UUID | None, ip: str | None
    ) -> None:
        keys = [f"contact:phone:{payload.mobile}"]
        if ip is not None:
            keys.append(f"contact:ip:{ip}")
        async with self._session.begin():
            for key in sorted(keys):
                await self._session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key}
                )
            now = utc_now()
            if ip is not None:
                await self._check_cap(
                    "ip", self._settings.contact_max_per_ip, ContactMessage.ip == ip, now
                )
            await self._check_cap(
                "phone",
                self._settings.contact_max_per_phone,
                ContactMessage.phone == payload.mobile,
                now,
            )
            self._session.add(
                ContactMessage(
                    user_id=user_id,
                    name=payload.name,
                    phone=payload.mobile,
                    email=payload.email,
                    subject=payload.subject,
                    message=payload.message,
                    ip=ip,
                )
            )

    async def _check_cap(
        self, scope: str, cap: int, criterion: ColumnElement[bool], now: datetime
    ) -> None:
        """429 when ``cap`` messages fall inside the window; retry when the oldest leaves it."""
        window = timedelta(seconds=self._settings.contact_window_seconds)
        oldest_counted = await self._session.scalar(
            select(ContactMessage.created_at)
            .where(criterion, ContactMessage.created_at > now - window)
            .order_by(ContactMessage.created_at.desc())
            .offset(cap - 1)
            .limit(1)
        )
        if oldest_counted is None:
            return
        raise RateLimitedError(
            retry_after=max(1, math.ceil((oldest_counted + window - now).total_seconds())),
            message="Too many messages",
            details=[{"type": f"too_many_messages_{scope}"}],
        )

    async def list_messages(
        self, filters: ContactFilters, params: PageParams
    ) -> Page[AdminContactSummary]:
        statement = select(ContactMessage)
        if filters.status is not None:
            statement = statement.where(ContactMessage.status == filters.status)
        async with self._session.begin():
            rows, total = await paginate(
                self._session,
                statement,
                (ContactMessage.created_at.desc(),),
                tie_breaker=ContactMessage.id,
                params=params,
            )
        items = [AdminContactSummary.model_validate(row[0]) for row in rows]
        return Page.build(items, total=total, params=params)

    async def get(self, message_id: UUID) -> AdminContactDetail:
        async with self._session.begin():
            return AdminContactDetail.model_validate(await self._find(message_id))

    async def update(
        self,
        actor: CurrentUser,
        message_id: UUID,
        payload: UpdateContactRequest,
        request: Request,
    ) -> AdminContactDetail:
        sent = payload.model_dump(exclude_unset=True)
        async with self._session.begin():
            message = await self._find(message_id, lock=True)
            before: dict[str, Any] = {}
            after: dict[str, Any] = {}
            new_status = sent.get("status")
            if new_status is not None and new_status != message.status:
                if new_status not in _TRANSITIONS[message.status]:
                    raise BusinessRuleError(
                        code=ErrorCode.INVALID_STATE_TRANSITION,
                        message=f"A {message.status} message cannot become {new_status}",
                    )
                before["status"] = message.status
                after["status"] = new_status
                message.status = new_status
            if "internal_note" in sent and sent["internal_note"] != message.internal_note:
                # Only the fact of the change: the note may quote the customer.
                after["internal_note_changed"] = True
                message.internal_note = sent["internal_note"]
            if after:
                message.handled_by = actor.id
                await self._session.flush()
                await record_audit(
                    self._session,
                    actor_id=actor.id,
                    action="contact_message.updated",
                    entity_type=_ENTITY,
                    entity_id=message.id,
                    before=before,
                    after=after,
                    request=request,
                )
                await self._session.refresh(message)
            return AdminContactDetail.model_validate(message)

    async def _find(self, message_id: UUID, *, lock: bool = False) -> ContactMessage:
        statement = select(ContactMessage).where(ContactMessage.id == message_id)
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        message = (await self._session.scalars(statement)).one_or_none()
        if message is None:
            raise NotFoundError(message="Contact message not found")
        return message
