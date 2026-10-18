"""Admin discount codes: list, detail, create, update, soft delete (DSC-04, ADR-044).

Every write locks the code row ``FOR UPDATE`` (the lock ``RedemptionService.redeem`` takes),
so an edit never interleaves with an order counting the code's limits. Changes affect
later orders only: existing redemptions are never touched. Lowering a limit below the
current count is allowed; it only blocks new uses.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from fastapi import Request
from sqlalchemy import ColumnElement, UnaryExpression, and_, case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BadRequestError, BusinessRuleError, ConflictError, NotFoundError
from app.core.time import utc_now
from app.db.models import DiscountCode, DiscountRedemption, DiscountType, RedemptionStatus
from app.modules.auth.service import CurrentUser
from app.modules.discounts.admin_schemas import (
    EDITABLE_FIELDS,
    CreateDiscountRequest,
    DiscountResponse,
    UpdateDiscountRequest,
    check_combination,
)
from app.shared.audit import record_audit
from app.shared.pagination import Page, PageParams, escape_like, paginate

MANAGE_PERMISSION: Final = "discounts:manage"
STATES: Final = ("active", "scheduled", "expired", "inactive")
_AUDITED: Final = ("code", "type", *EDITABLE_FIELDS)


@dataclass(frozen=True, slots=True)
class DiscountFilters:
    q: str | None = None
    state: str | None = None


def _not_found() -> NotFoundError:
    return NotFoundError(message="Discount code not found")


def _invalid(field: str, message: str) -> BadRequestError:
    return BadRequestError(
        message="Request validation failed",
        details=[{"field": field, "message": message, "type": "value_error"}],
    )


def _snapshot(code: DiscountCode) -> dict[str, Any]:
    return {field: getattr(code, field) for field in _AUDITED}


def _state_clause(state: str, now: datetime) -> ColumnElement[bool]:
    started = or_(DiscountCode.starts_at.is_(None), DiscountCode.starts_at <= now)
    running = or_(DiscountCode.ends_at.is_(None), DiscountCode.ends_at > now)
    active = DiscountCode.is_active.is_(True)
    clauses: dict[str, ColumnElement[bool]] = {
        "active": and_(active, started, running),
        "scheduled": and_(active, DiscountCode.starts_at > now),
        "expired": and_(active, DiscountCode.ends_at <= now),
        "inactive": DiscountCode.is_active.is_(False),
    }
    return clauses[state]


class AdminDiscountService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_codes(
        self,
        filters: DiscountFilters,
        order_by: Sequence[UnaryExpression[Any]],
        params: PageParams,
        now: datetime | None = None,
    ) -> Page[DiscountResponse]:
        now = now or utc_now()
        statement = select(DiscountCode).where(DiscountCode.deleted_at.is_(None))
        if filters.q is not None:
            statement = statement.where(
                DiscountCode.code.ilike(f"%{escape_like(filters.q)}%", escape="\\")
            )
        if filters.state is not None:
            statement = statement.where(_state_clause(filters.state, now))
        async with self._session.begin():
            rows, total = await paginate(
                self._session, statement, order_by, tie_breaker=DiscountCode.id, params=params
            )
            codes = [row[0] for row in rows]
            counts = await self._counts([code.id for code in codes])
        items = [self._response(code, counts.get(code.id)) for code in codes]
        return Page.build(items, total=total, params=params)

    async def get(self, code_id: UUID) -> DiscountResponse:
        async with self._session.begin():
            code = await self._live(code_id)
            counts = await self._counts([code.id])
        return self._response(code, counts.get(code.id))

    async def create(
        self, actor: CurrentUser, payload: CreateDiscountRequest, request: Request
    ) -> DiscountResponse:
        code = DiscountCode(
            **payload.model_dump(),
            created_by=actor.id,
            updated_by=actor.id,
        )
        try:
            async with self._session.begin():
                existing = await self._session.scalar(
                    select(DiscountCode.id).where(
                        DiscountCode.code == payload.code, DiscountCode.deleted_at.is_(None)
                    )
                )
                if existing is not None:
                    raise _duplicate()
                self._session.add(code)
                await self._session.flush()
                await record_audit(
                    self._session,
                    actor_id=actor.id,
                    action="discount.created",
                    entity_type="discount_code",
                    entity_id=code.id,
                    before=None,
                    after=_snapshot(code),
                    request=request,
                )
        except IntegrityError as error:
            # A concurrent create of the same text won the race.
            if "uq_discount_codes_code" in str(error.orig):
                raise _duplicate() from error
            raise
        return self._response(code, None)

    async def update(
        self,
        actor: CurrentUser,
        code_id: UUID,
        payload: UpdateDiscountRequest,
        request: Request,
    ) -> DiscountResponse:
        sent = payload.model_dump(exclude_unset=True)
        async with self._session.begin():
            code = await self._live(code_id, lock=True)
            for field in ("code", "type"):
                if field in sent and sent.pop(field) != getattr(code, field):
                    raise _invalid(field, "Cannot change once created; create a new code")
            merged = {field: sent.get(field, getattr(code, field)) for field in EDITABLE_FIELDS}
            problem = check_combination(type=DiscountType(code.type), **_rule_fields(merged))
            if problem is not None:
                raise BusinessRuleError(
                    message=problem, details=[{"field": "body", "type": "conflicts_with_stored"}]
                )
            before = _snapshot(code)
            changed = {
                field: value for field, value in sent.items() if getattr(code, field) != value
            }
            if changed:
                for field, value in changed.items():
                    setattr(code, field, value)
                code.updated_by = actor.id
                await self._session.flush()
                await record_audit(
                    self._session,
                    actor_id=actor.id,
                    action="discount.updated",
                    entity_type="discount_code",
                    entity_id=code.id,
                    before={field: before[field] for field in changed},
                    after=changed,
                    request=request,
                )
            counts = await self._counts([code.id])
        return self._response(code, counts.get(code.id))

    async def delete(self, actor: CurrentUser, code_id: UUID, request: Request) -> None:
        async with self._session.begin():
            code = await self._live(code_id, lock=True)
            code.soft_delete()
            code.updated_by = actor.id
            await self._session.flush()
            await record_audit(
                self._session,
                actor_id=actor.id,
                action="discount.deleted",
                entity_type="discount_code",
                entity_id=code.id,
                before={"code": code.code},
                after={"deleted": True},
                request=request,
            )

    async def _live(self, code_id: UUID, *, lock: bool = False) -> DiscountCode:
        statement = select(DiscountCode).where(
            DiscountCode.id == code_id, DiscountCode.deleted_at.is_(None)
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        code = (await self._session.scalars(statement)).one_or_none()
        if code is None:
            raise _not_found()
        return code

    async def _counts(self, code_ids: Sequence[UUID]) -> dict[UUID, tuple[int, int, int]]:
        """Pending, confirmed and released uses per code, in one grouped query."""
        if not code_ids:
            return {}

        def counted(status: RedemptionStatus) -> Any:
            return func.count(case((DiscountRedemption.status == status, 1)))

        statement = (
            select(
                DiscountRedemption.discount_code_id,
                counted(RedemptionStatus.PENDING),
                counted(RedemptionStatus.CONFIRMED),
                counted(RedemptionStatus.RELEASED),
            )
            .where(DiscountRedemption.discount_code_id.in_(code_ids))
            .group_by(DiscountRedemption.discount_code_id)
        )
        counts: dict[UUID, tuple[int, int, int]] = {}
        for row in await self._session.execute(statement):
            code_id: UUID = row[0]
            counts[code_id] = (int(row[1]), int(row[2]), int(row[3]))
        return counts

    @staticmethod
    def _response(code: DiscountCode, counts: tuple[int, int, int] | None) -> DiscountResponse:
        pending, confirmed, released = counts or (0, 0, 0)
        stored = {
            field: getattr(code, field)
            for field in DiscountResponse.model_fields
            if not field.endswith("_count")
        }
        return DiscountResponse.model_validate(
            stored
            | {"pending_count": pending, "confirmed_count": confirmed, "released_count": released}
        )


def _duplicate() -> ConflictError:
    return ConflictError(
        message="A live discount code with this text exists",
        details=[{"field": "code", "type": "duplicate"}],
    )


def _rule_fields(merged: dict[str, Any]) -> dict[str, Any]:
    return {
        "value": merged["value"],
        "max_amount": merged["max_amount"],
        "starts_at": merged["starts_at"],
        "ends_at": merged["ends_at"],
        "usage_limit_total": merged["usage_limit_total"],
        "usage_limit_per_user": merged["usage_limit_per_user"],
    }
