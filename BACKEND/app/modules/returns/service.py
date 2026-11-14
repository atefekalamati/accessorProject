"""The customer's return requests (ORD-08, PRD «مرجوعی» ✓, ADR-063).

Create runs in one transaction in the global lock order (ADR-048, see ``state``):
Idempotency-Key → order advisory lock → order row ``FOR UPDATE``; the quantity still
returnable is read only after those locks, so two requests cannot over-claim a line.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import UnaryExpression

from app.core.errors import BusinessRuleError, NotFoundError
from app.core.time import utc_now
from app.db.models import (
    Order,
    OrderItem,
    ReturnItem,
    ReturnRequest,
    ReturnStatus,
    ReturnStatusHistory,
    ShipmentStatus,
)
from app.modules.orders.cancel import lock_order, order_advisory_lock
from app.modules.returns.repository import ReturnRepository
from app.modules.returns.schemas import (
    CreateReturnRequest,
    ReturnableItemResponse,
    ReturnHistoryResponse,
    ReturnItemResponse,
    ReturnResponse,
    ReturnSummaryResponse,
)
from app.modules.returns.state import (
    check_transition,
    return_deadline,
    returnable_quantity,
    window_open,
)
from app.shared.audit import record_audit
from app.shared.idempotency import IdempotencyService, request_hash
from app.shared.pagination import Page, PageParams, paginate

SCOPE: Final = "returns.create"


@dataclass(frozen=True, slots=True)
class CreatedReturn:
    status_code: int
    body: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ReturnFacts:
    """What the order detail shows about returns (ACC-01 + ORD-08)."""

    deadline: datetime | None
    can_return: bool
    items: list[ReturnableItemResponse]


def _order_not_found() -> NotFoundError:
    # Someone else's order and an unknown one get the same answer (no existence leak).
    return NotFoundError(message="Order not found")


def _return_not_found() -> NotFoundError:
    return NotFoundError(message="Return request not found")


def _rule(message: str, details: list[dict[str, Any]]) -> BusinessRuleError:
    return BusinessRuleError(message=message, details=details)


def _delivered(shipment_status: str, delivered_at: datetime | None) -> datetime | None:
    """When the order was delivered, or None: only the status plus a recorded time count."""
    if shipment_status != ShipmentStatus.DELIVERED or delivered_at is None:
        return None
    return delivered_at


async def return_facts(
    session: AsyncSession,
    *,
    order_id: UUID,
    shipment_status: str,
    items: Sequence[OrderItem],
    window_days: int,
    now: datetime,
) -> ReturnFacts:
    """Deadline, ``can_return`` and what is left per line (read only)."""
    repository = ReturnRepository(session)
    delivered_at = _delivered(shipment_status, await repository.delivered_at(order_id))
    claimed = await repository.claimed(order_id)
    left = [
        ReturnableItemResponse(
            order_item_id=item.id,
            position=item.position,
            returnable_quantity=(
                0
                if delivered_at is None
                else returnable_quantity(item.quantity, claimed.get(item.id, 0))
            ),
        )
        for item in items
    ]
    if delivered_at is None:
        return ReturnFacts(deadline=None, can_return=False, items=left)
    is_open = window_open(delivered_at, window_days, now)
    return ReturnFacts(
        deadline=return_deadline(delivered_at, window_days),
        can_return=is_open and any(line.returnable_quantity > 0 for line in left),
        items=left
        if is_open
        else [line.model_copy(update={"returnable_quantity": 0}) for line in left],
    )


class ReturnService:
    def __init__(self, session: AsyncSession, *, window_days: int) -> None:
        self._session = session
        self._window_days = window_days
        self._repository = ReturnRepository(session)

    async def create(
        self,
        user_id: UUID,
        order_number: str,
        key: str,
        payload: CreateReturnRequest,
        request: Request | None = None,
        now: datetime | None = None,
    ) -> CreatedReturn:
        hash_ = request_hash(path={"order_number": order_number}, body=payload.canonical())
        async with self._session.begin():
            idempotency = IdempotencyService(self._session)
            stored = await idempotency.begin(
                user_id=user_id, scope=SCOPE, key=key, request_hash=hash_
            )
            if stored is not None:
                body = stored.body if isinstance(stored.body, dict) else {}
                return CreatedReturn(status_code=stored.status_code, body=body)
            # Existence (and ownership) before the advisory lock: no contention on others.
            order_id = await self._repository.owned_order_id(user_id, order_number)
            if order_id is None:
                raise _order_not_found()
            await self._session.execute(order_advisory_lock(order_id))
            order = await lock_order(self._session, order_id, user_id=user_id)
            if order is None:
                raise _order_not_found()
            now = now or utc_now()
            delivered_at = _delivered(
                order.shipment_status, await self._repository.delivered_at(order.id)
            )
            if delivered_at is None:
                raise _rule(
                    "Only a delivered order can be returned", [{"type": "order_not_delivered"}]
                )
            if not window_open(delivered_at, self._window_days, now):
                raise _rule(
                    "The return window of this order has closed",
                    [{"type": "return_window_closed"}],
                )
            lines = {item.id: item for item in await self._repository.order_items(order.id)}
            claimed = await self._repository.claimed(order.id)  # after the locks
            unknown = [
                str(line.order_item_id) for line in payload.items if line.order_item_id not in lines
            ]
            if unknown:
                raise _rule(
                    "An item is not part of this order",
                    [
                        {"field": "items", "type": "item_not_in_order", "order_item_id": item}
                        for item in unknown
                    ],
                )
            over = []
            for line in payload.items:
                left = returnable_quantity(
                    lines[line.order_item_id].quantity, claimed.get(line.order_item_id, 0)
                )
                if line.quantity > left:
                    over.append(
                        {
                            "field": "items",
                            "type": "quantity_exceeds_returnable",
                            "order_item_id": str(line.order_item_id),
                            "returnable_quantity": left,
                        }
                    )
            if over:
                raise _rule("More than the returnable quantity was requested", over)
            created = ReturnRequest(
                order_id=order.id,
                user_id=order.user_id,
                status=ReturnStatus.REQUESTED,
                reason=payload.reason,
                note=payload.note,
            )
            self._session.add(created)
            await self._session.flush()
            self._session.add_all(
                ReturnItem(
                    return_request_id=created.id,
                    order_item_id=line.order_item_id,
                    quantity=line.quantity,
                )
                for line in payload.items
            )
            self._session.add(
                ReturnStatusHistory(
                    return_request_id=created.id,
                    old_status=None,
                    new_status=ReturnStatus.REQUESTED,
                    actor_user_id=user_id,
                )
            )
            await self._session.flush()
            await record_audit(
                self._session,
                actor_id=user_id,
                action="return.requested",
                entity_type="return_request",
                entity_id=created.id,
                before=None,
                after={
                    "order_number": order.order_number,
                    "reason": payload.reason.value,
                    "lines": len(payload.items),
                    "quantity": sum(line.quantity for line in payload.items),
                },
                request=request,
            )
            body = (await self._view(created, order.order_number)).model_dump(mode="json")
            await idempotency.complete(
                user_id=user_id,
                scope=SCOPE,
                key=key,
                request_hash=hash_,
                status_code=201,
                body=body,
            )
        return CreatedReturn(status_code=201, body=body)

    async def list_returns(
        self,
        user_id: UUID,
        *,
        status: ReturnStatus | None,
        order_by: Sequence[UnaryExpression[Any]],
        paging: PageParams,
    ) -> Page[ReturnSummaryResponse]:
        quantity = (
            select(func.coalesce(func.sum(ReturnItem.quantity), 0))
            .where(ReturnItem.return_request_id == ReturnRequest.id)
            .scalar_subquery()
        )
        statement = (
            select(ReturnRequest, Order.order_number, quantity)
            .join(Order, Order.id == ReturnRequest.order_id)
            .where(ReturnRequest.user_id == user_id)
        )
        if status is not None:
            statement = statement.where(ReturnRequest.status == status)
        async with self._session.begin():
            rows, total = await paginate(
                self._session, statement, order_by, tie_breaker=ReturnRequest.id, params=paging
            )
        items = [
            ReturnSummaryResponse(
                id=row[0].id,
                order_number=row[1],
                status=row[0].status,
                reason=row[0].reason,
                item_count=int(row[2]),
                refund_amount=row[0].refund_amount,
                created_at=row[0].created_at,
            )
            for row in rows
        ]
        return Page.build(items, total=total, params=paging)

    async def detail(self, user_id: UUID, return_id: UUID) -> ReturnResponse:
        async with self._session.begin():
            found = await self._repository.owned_request(user_id, return_id)
            if found is None:
                raise _return_not_found()
            return await self._view(found, await self._repository.order_number(found.order_id))

    async def cancel(
        self, user_id: UUID, return_id: UUID, request: Request | None = None
    ) -> ReturnResponse:
        """``requested`` → ``cancelled``; already cancelled answers as it is (idempotent).

        Locks only the request row (see ``state``): it frees quantity and touches no order,
        stock or money.
        """
        async with self._session.begin():
            found = await self._repository.owned_request(user_id, return_id, lock=True)
            if found is None:
                raise _return_not_found()
            if found.status != ReturnStatus.CANCELLED:
                check_transition(found.status, ReturnStatus.CANCELLED)
                found.status = ReturnStatus.CANCELLED
                self._session.add(
                    ReturnStatusHistory(
                        return_request_id=found.id,
                        old_status=ReturnStatus.REQUESTED,
                        new_status=ReturnStatus.CANCELLED,
                        actor_user_id=user_id,
                    )
                )
                await self._session.flush()
                await record_audit(
                    self._session,
                    actor_id=user_id,
                    action="return.cancelled",
                    entity_type="return_request",
                    entity_id=found.id,
                    before={"status": ReturnStatus.REQUESTED.value},
                    after={"status": ReturnStatus.CANCELLED.value},
                    request=request,
                )
                await self._session.refresh(found)
            return await self._view(found, await self._repository.order_number(found.order_id))

    async def _view(self, found: ReturnRequest, order_number: str) -> ReturnResponse:
        lines = await self._repository.items_with_lines(found.id)
        history = await self._repository.history(found.id)
        return ReturnResponse(
            id=found.id,
            order_number=order_number,
            status=found.status,
            reason=found.reason,
            note=found.note,
            reject_reason=found.reject_reason if found.status == ReturnStatus.REJECTED else None,
            items=[
                ReturnItemResponse(
                    order_item_id=item.order_item_id,
                    product_title=line.product_title,
                    variant_label=line.variant_label,
                    quantity=item.quantity,
                    accepted_quantity=item.accepted_quantity,
                    refund_amount=item.refund_amount,
                )
                for item, line in lines
            ],
            refund_amount=found.refund_amount,
            refunded_at=found.refunded_at,
            history=[
                ReturnHistoryResponse(status=row.new_status, created_at=row.created_at)
                for row in history
            ],
            created_at=found.created_at,
            updated_at=found.updated_at,
        )
