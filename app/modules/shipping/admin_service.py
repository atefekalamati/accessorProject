"""Admin shipping methods: list, detail, create, update, soft delete (ADDR-03, ADR-045).

Every write locks the row ``FOR UPDATE`` so concurrent edits are serialized and each audit
row's ``before`` is the previous edit's ``after``. A cost change affects later orders only:
orders keep a snapshot of the method and its amount (ORD-01).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final
from uuid import UUID

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.db.models import ShippingMethod
from app.modules.auth.service import CurrentUser
from app.modules.shipping.admin_schemas import (
    EDITABLE_FIELDS,
    AdminShippingMethodResponse,
    CreateShippingMethodRequest,
    UpdateShippingMethodRequest,
)
from app.shared.audit import record_audit
from app.shared.pagination import Page, PageParams, escape_like, paginate

MANAGE_PERMISSION: Final = "shipping:manage"
STATES: Final = ("active", "inactive")
_ENTITY: Final = "shipping_method"


@dataclass(frozen=True, slots=True)
class ShippingMethodFilters:
    q: str | None = None
    state: str | None = None


def _not_found() -> NotFoundError:
    return NotFoundError(message="Shipping method not found")


def _snapshot(method: ShippingMethod) -> dict[str, Any]:
    return {field: getattr(method, field) for field in EDITABLE_FIELDS}


def _response(method: ShippingMethod) -> AdminShippingMethodResponse:
    return AdminShippingMethodResponse.model_validate(method)


class AdminShippingService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_methods(
        self, filters: ShippingMethodFilters, params: PageParams
    ) -> Page[AdminShippingMethodResponse]:
        statement = select(ShippingMethod).where(ShippingMethod.deleted_at.is_(None))
        if filters.q is not None:
            statement = statement.where(
                ShippingMethod.title.ilike(f"%{escape_like(filters.q)}%", escape="\\")
            )
        if filters.state is not None:
            statement = statement.where(ShippingMethod.is_active.is_(filters.state == "active"))
        async with self._session.begin():
            rows, total = await paginate(
                self._session,
                statement,
                (ShippingMethod.display_order.asc(), ShippingMethod.title.asc()),
                tie_breaker=ShippingMethod.id,
                params=params,
            )
        return Page.build([_response(row[0]) for row in rows], total=total, params=params)

    async def get(self, method_id: UUID) -> AdminShippingMethodResponse:
        async with self._session.begin():
            return _response(await self._live(method_id))

    async def create(
        self, actor: CurrentUser, payload: CreateShippingMethodRequest, request: Request
    ) -> AdminShippingMethodResponse:
        method = ShippingMethod(**payload.model_dump())
        async with self._session.begin():
            self._session.add(method)
            await self._session.flush()
            await record_audit(
                self._session,
                actor_id=actor.id,
                action="shipping_method.created",
                entity_type=_ENTITY,
                entity_id=method.id,
                before=None,
                after=_snapshot(method),
                request=request,
            )
            await self._session.refresh(method)
        return _response(method)

    async def update(
        self,
        actor: CurrentUser,
        method_id: UUID,
        payload: UpdateShippingMethodRequest,
        request: Request,
    ) -> AdminShippingMethodResponse:
        sent = payload.model_dump(exclude_unset=True)
        async with self._session.begin():
            method = await self._live(method_id, lock=True)
            changed = {
                field: value for field, value in sent.items() if getattr(method, field) != value
            }
            if changed:
                before = {field: getattr(method, field) for field in changed}
                for field, value in changed.items():
                    setattr(method, field, value)
                await self._session.flush()
                await record_audit(
                    self._session,
                    actor_id=actor.id,
                    action="shipping_method.updated",
                    entity_type=_ENTITY,
                    entity_id=method.id,
                    before=before,
                    after=changed,
                    request=request,
                )
                await self._session.refresh(method)
        return _response(method)

    async def delete(self, actor: CurrentUser, method_id: UUID, request: Request) -> None:
        async with self._session.begin():
            method = await self._live(method_id, lock=True)
            method.soft_delete()
            await self._session.flush()
            await record_audit(
                self._session,
                actor_id=actor.id,
                action="shipping_method.deleted",
                entity_type=_ENTITY,
                entity_id=method.id,
                before=_snapshot(method),
                after={"deleted": True},
                request=request,
            )

    async def _live(self, method_id: UUID, *, lock: bool = False) -> ShippingMethod:
        statement = select(ShippingMethod).where(
            ShippingMethod.id == method_id, ShippingMethod.deleted_at.is_(None)
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        method = (await self._session.scalars(statement)).one_or_none()
        if method is None:
            raise _not_found()
        return method
