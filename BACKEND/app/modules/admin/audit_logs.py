"""The audit log viewer for super admins (ADM-06, PRD «گزارش ممیزی» ✓).

Read only: the audit log cannot be changed or deleted (database trigger). Metadata is
shown as stored, already redacted and masked when it was written.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Any, Final
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog
from app.db.session import get_db_session
from app.modules.auth.dependencies import require_permission
from app.shared.idempotency import NO_STORE
from app.shared.pagination import (
    Page,
    PageParams,
    admin_page_params,
    allowed_query_params,
    escape_like,
    paginate,
)
from app.shared.search import TimeRange, invalid_query, time_range

router = APIRouter(prefix="/admin/audit-logs", tags=["admin-audit"])

# "order.status_changed" exactly, or a prefix ending in a dot such as "order.".
_ACTION: Final = re.compile(r"[a-z_]+(\.[a-z_]*)?")
_ENTITY_TYPE: Final = re.compile(r"[a-z_]{1,50}")


class AuditLogResponse(BaseModel):
    id: UUID
    actor_user_id: UUID | None
    action: str
    entity_type: str
    entity_id: UUID | None
    metadata: dict[str, Any]
    ip: str | None
    created_at: datetime


@router.get(
    "",
    response_model=Page[AuditLogResponse],
    summary="Search the audit log (super admin only), newest first",
    # Authorization first, so an unauthenticated caller learns nothing from validation.
    dependencies=[
        Depends(require_permission("audit:read")),
        Depends(
            allowed_query_params(
                "page", "limit", "actor_user_id", "action", "entity_type", "entity_id", "from", "to"
            )
        ),
    ],
)
async def list_audit_logs(
    paging: Annotated[PageParams, Depends(admin_page_params)],
    created: Annotated[TimeRange, Depends(time_range)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    actor_user_id: UUID | None = None,
    action: Annotated[str | None, Query(max_length=100)] = None,
    entity_type: Annotated[str | None, Query(max_length=50)] = None,
    entity_id: UUID | None = None,
) -> JSONResponse:
    criteria: list[ColumnElement[bool]] = []
    if actor_user_id is not None:
        criteria.append(AuditLog.actor_user_id == actor_user_id)
    if action is not None:
        if _ACTION.fullmatch(action) is None:
            raise invalid_query("action", "Must be an action like 'order.created' or 'order.'")
        if action.endswith("."):
            criteria.append(AuditLog.action.like(f"{escape_like(action)}%", escape="\\"))
        else:
            criteria.append(AuditLog.action == action)
    if entity_type is not None:
        if _ENTITY_TYPE.fullmatch(entity_type) is None:
            raise invalid_query("entity_type", "Must be lowercase letters and '_'")
        criteria.append(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        criteria.append(AuditLog.entity_id == entity_id)
    if created.start is not None:
        criteria.append(AuditLog.created_at >= created.start)
    if created.end is not None:
        criteria.append(AuditLog.created_at < created.end)
    async with session.begin():
        rows, total = await paginate(
            session,
            select(AuditLog).where(*criteria),
            [AuditLog.created_at.desc()],
            tie_breaker=AuditLog.id.desc(),
            params=paging,
        )
    items = [
        AuditLogResponse(
            id=row.id,
            actor_user_id=row.actor_user_id,
            action=row.action,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            metadata=row.metadata_,
            ip=None if row.ip is None else str(row.ip),
            created_at=row.created_at,
        )
        for (row,) in rows
    ]
    page = Page.build(items, total=total, params=paging)
    return JSONResponse(content=page.model_dump(mode="json"), headers=dict(NO_STORE))
