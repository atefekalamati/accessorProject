"""Staff side of return requests up to inspection (ORD-09, PRD «مرجوعی» ✓, ADR-063).

Every write takes the global lock order (see ``state``): order advisory lock → order row
``FOR UPDATE`` → return request row ``FOR UPDATE``; inspection then share-locks the
restocked variants in id order and locks their default-warehouse items in variant order,
the same variant/item order as reservations (ADR-034), so it cannot deadlock with them.
Stock goes back only for ``sellable`` units, once: inspection runs only from
``received`` under the request lock.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any, Final
from uuid import UUID

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import UnaryExpression

from app.core.errors import BadRequestError, BusinessRuleError, NotFoundError
from app.core.time import utc_now
from app.db.models import (
    InventoryItem,
    ItemCondition,
    MovementType,
    Order,
    OrderItem,
    ProductVariant,
    ReturnItem,
    ReturnRequest,
    ReturnStatus,
    ReturnStatusHistory,
)
from app.db.models.common import not_deleted
from app.modules.auth.service import CurrentUser
from app.modules.inventory.movements import Counters, record_movement
from app.modules.inventory.repository import InventoryRepository
from app.modules.orders.cancel import lock_order, order_advisory_lock
from app.modules.returns.admin_schemas import (
    AdminReturnHistoryResponse,
    AdminReturnItemResponse,
    AdminReturnResponse,
    AdminReturnSummaryResponse,
    InspectReturnRequest,
    RejectReturnRequest,
    ReturnNoteRequest,
)
from app.modules.returns.repository import ReturnRepository
from app.modules.returns.state import check_transition
from app.shared.audit import record_audit
from app.shared.inventory import MAX_STOCK_QUANTITY
from app.shared.pagination import Page, PageParams, paginate

logger = logging.getLogger(__name__)

RETURN_REFERENCE: Final = "return"


def _not_found() -> NotFoundError:
    return NotFoundError(message="Return request not found")


def _bad_lines(kind: str, ids: Sequence[UUID | str]) -> BadRequestError:
    return BadRequestError(
        message="The inspection must list every line of the request once",
        details=[{"field": "items", "type": kind, "order_item_id": str(i)} for i in ids],
    )


class AdminReturnService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repository = ReturnRepository(session)

    # --- reads -----------------------------------------------------------------------

    async def list_returns(
        self,
        *,
        status: ReturnStatus | None,
        order_by: Sequence[UnaryExpression[Any]],
        paging: PageParams,
    ) -> Page[AdminReturnSummaryResponse]:
        quantity = (
            select(func.coalesce(func.sum(ReturnItem.quantity), 0))
            .where(ReturnItem.return_request_id == ReturnRequest.id)
            .scalar_subquery()
        )
        statement = select(ReturnRequest, Order.order_number, quantity).join(
            Order, Order.id == ReturnRequest.order_id
        )
        if status is not None:
            statement = statement.where(ReturnRequest.status == status)
        async with self._session.begin():
            rows, total = await paginate(
                self._session, statement, order_by, tie_breaker=ReturnRequest.id, params=paging
            )
        items = [
            AdminReturnSummaryResponse(
                id=row[0].id,
                order_number=row[1],
                status=row[0].status,
                reason=row[0].reason,
                item_count=int(row[2]),
                refund_amount=row[0].refund_amount,
                created_at=row[0].created_at,
                updated_at=row[0].updated_at,
            )
            for row in rows
        ]
        return Page.build(items, total=total, params=paging)

    async def detail(self, return_id: UUID) -> AdminReturnResponse:
        async with self._session.begin():
            found = await self._session.get(ReturnRequest, return_id)
            if found is None:
                raise _not_found()
            return await self.view(found)

    # --- transitions -----------------------------------------------------------------

    async def approve(
        self, actor: CurrentUser, return_id: UUID, payload: ReturnNoteRequest, request: Request
    ) -> AdminReturnResponse:
        async with self._session.begin():
            found = await self.lock(return_id)
            if found.status != ReturnStatus.APPROVED:
                check_transition(found.status, ReturnStatus.APPROVED)
                found.decided_at, found.decided_by = utc_now(), actor.id
                if payload.admin_note is not None:
                    found.admin_note = payload.admin_note
                await self._move(found, ReturnStatus.APPROVED, actor.id)
                await self._audit(
                    found, "return.approved", actor.id, ReturnStatus.REQUESTED, request
                )
            return await self._fresh_view(found)

    async def reject(
        self, actor: CurrentUser, return_id: UUID, payload: RejectReturnRequest, request: Request
    ) -> AdminReturnResponse:
        async with self._session.begin():
            found = await self.lock(return_id)
            if found.status != ReturnStatus.REJECTED:
                check_transition(found.status, ReturnStatus.REJECTED)
                found.reject_reason = payload.reject_reason
                found.decided_at, found.decided_by = utc_now(), actor.id
                if payload.admin_note is not None:
                    found.admin_note = payload.admin_note
                await self._move(found, ReturnStatus.REJECTED, actor.id)
                await self._audit(
                    found, "return.rejected", actor.id, ReturnStatus.REQUESTED, request
                )
            return await self._fresh_view(found)

    async def receive(
        self, actor: CurrentUser, return_id: UUID, payload: ReturnNoteRequest, request: Request
    ) -> AdminReturnResponse:
        async with self._session.begin():
            found = await self.lock(return_id)
            if found.status != ReturnStatus.RECEIVED:
                check_transition(found.status, ReturnStatus.RECEIVED)
                found.received_at = utc_now()
                if payload.admin_note is not None:
                    found.admin_note = payload.admin_note
                await self._move(found, ReturnStatus.RECEIVED, actor.id)
                await self._audit(
                    found, "return.received", actor.id, ReturnStatus.APPROVED, request
                )
            return await self._fresh_view(found)

    async def inspect(
        self, actor: CurrentUser, return_id: UUID, payload: InspectReturnRequest, request: Request
    ) -> AdminReturnResponse:
        async with self._session.begin():
            found = await self.lock(return_id)
            # Only from received: a second inspection (retry or race) is 422 and restocks
            # nothing, because the status is checked under the request lock.
            check_transition(found.status, ReturnStatus.INSPECTED)
            lines = await self._repository.items_with_lines(found.id)
            by_line = {item.order_item_id: (item, line) for item, line in lines}
            sent = {entry.order_item_id: entry for entry in payload.items}
            unknown = [i for i in sent if i not in by_line]
            if unknown:
                raise _bad_lines("item_not_in_request", unknown)
            missing = [i for i in by_line if i not in sent]
            if missing:
                raise _bad_lines("item_missing", missing)
            over = [
                i for i, entry in sent.items() if entry.accepted_quantity > by_line[i][0].quantity
            ]
            if over:
                raise _bad_lines("accepted_exceeds_quantity", over)

            restock: dict[UUID, int] = {}
            for order_item_id, entry in sent.items():
                if entry.condition is ItemCondition.SELLABLE and entry.accepted_quantity > 0:
                    variant_id = by_line[order_item_id][1].variant_id
                    restock[variant_id] = restock.get(variant_id, 0) + entry.accepted_quantity
            live, items = await self._lock_stock(sorted(restock))
            for variant_id in sorted(live):
                item = items[variant_id]
                if item.total_quantity + restock[variant_id] > MAX_STOCK_QUANTITY:
                    raise BusinessRuleError(
                        message="Returning these units would exceed the stock limit",
                        details=[{"type": "stock_limit", "variant_id": str(variant_id)}],
                    )

            # One movement per restocked line (the link column is unique), applied in a
            # stable order; the stock limit above was checked on the per-variant total.
            audit_lines = []
            for order_item_id, entry in sorted(sent.items(), key=lambda pair: str(pair[0])):
                item_row, line = by_line[order_item_id]
                item_row.condition = entry.condition.value
                item_row.accepted_quantity = entry.accepted_quantity
                item_row.refundable = entry.refundable
                item_row.inspection_note = entry.note
                wants = entry.condition is ItemCondition.SELLABLE and entry.accepted_quantity > 0
                restocked = 0
                if wants and line.variant_id in live:
                    item = items[line.variant_id]
                    before = Counters.of(item)
                    item.total_quantity += entry.accepted_quantity
                    movement = await record_movement(
                        self._session,
                        item,
                        movement_type=MovementType.RETURN,
                        quantity=entry.accepted_quantity,
                        before=before,
                        actor_id=actor.id,
                        reference=(RETURN_REFERENCE, found.id),
                    )
                    item_row.inventory_movement_id = movement.id
                    restocked = entry.accepted_quantity
                audit_lines.append(
                    {
                        "order_item_id": str(order_item_id),
                        "condition": entry.condition.value,
                        "accepted_quantity": entry.accepted_quantity,
                        "refundable": entry.refundable,
                        "restocked": restocked,
                        "restock_skipped": wants and line.variant_id not in live,
                    }
                )
            found.inspected_at = utc_now()
            if payload.admin_note is not None:
                found.admin_note = payload.admin_note
            await self._move(found, ReturnStatus.INSPECTED, actor.id)
            await record_audit(
                self._session,
                actor_id=actor.id,
                action="return.inspected",
                entity_type="return_request",
                entity_id=found.id,
                before={"status": ReturnStatus.RECEIVED.value},
                after={"status": ReturnStatus.INSPECTED.value, "lines": audit_lines},
                request=request,
            )
            view = await self._fresh_view(found)
        logger.info(
            "return.inspected",
            extra={
                "return_id": str(found.id),
                "restocked": {str(k): restock[k] for k in sorted(live)},
            },
        )
        return view

    # --- helpers ---------------------------------------------------------------------

    async def lock(self, return_id: UUID) -> ReturnRequest:
        """The request under the global lock order: order advisory → order → request."""
        order_id = await self._session.scalar(
            select(ReturnRequest.order_id).where(ReturnRequest.id == return_id)
        )
        if order_id is None:
            raise _not_found()
        await self._session.execute(order_advisory_lock(order_id))
        if await lock_order(self._session, order_id) is None:  # RESTRICT: never happens
            raise _not_found()
        found = await self._session.scalar(
            select(ReturnRequest)
            .where(ReturnRequest.id == return_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if found is None:
            raise _not_found()
        return found

    async def _lock_stock(
        self, variant_ids: list[UUID]
    ) -> tuple[set[UUID], dict[UUID, InventoryItem]]:
        """Share-lock the live variants (id order), then their items (variant order).

        A soft-deleted variant is skipped: its units are not put back (the inspection is
        still recorded and the audit says ``restock_skipped``).
        """
        if not variant_ids:
            return set(), {}
        rows = await self._session.execute(
            select(ProductVariant.id, ProductVariant.product_id)
            .where(ProductVariant.id.in_(variant_ids), not_deleted(ProductVariant))
            .order_by(ProductVariant.id)
            .with_for_update(read=True, of=ProductVariant)
        )
        live = {variant_id: product_id for variant_id, product_id in rows}
        # One item at a time in variant order (as reservations, ADR-034). The item exists
        # (the sale committed from it); if not, it is created like a manual increase.
        inventory = InventoryRepository(self._session)
        existing = {
            variant_id: await inventory.lock_default_item(variant_id, live[variant_id])
            for variant_id in sorted(live)
        }
        return set(live), existing

    async def _move(self, found: ReturnRequest, new: ReturnStatus, actor_id: UUID) -> None:
        old = found.status
        check_transition(old, new)
        found.status = new
        self._session.add(
            ReturnStatusHistory(
                return_request_id=found.id, old_status=old, new_status=new, actor_user_id=actor_id
            )
        )
        await self._session.flush()

    async def _audit(
        self,
        found: ReturnRequest,
        action: str,
        actor_id: UUID,
        before: ReturnStatus,
        request: Request,
    ) -> None:
        await record_audit(
            self._session,
            actor_id=actor_id,
            action=action,
            entity_type="return_request",
            entity_id=found.id,
            before={"status": before.value},
            after={"status": found.status},
            request=request,
        )

    async def _fresh_view(self, found: ReturnRequest) -> AdminReturnResponse:
        await self._session.flush()
        await self._session.refresh(found)
        return await self.view(found)

    async def view(self, found: ReturnRequest) -> AdminReturnResponse:
        lines = await self._repository.items_with_lines(found.id)
        history = await self._repository.history(found.id)
        return AdminReturnResponse(
            id=found.id,
            order_id=found.order_id,
            order_number=await self._repository.order_number(found.order_id),
            user_id=found.user_id,
            status=found.status,
            reason=found.reason,
            note=found.note,
            reject_reason=found.reject_reason,
            admin_note=found.admin_note,
            decided_by=found.decided_by,
            decided_at=found.decided_at,
            received_at=found.received_at,
            inspected_at=found.inspected_at,
            refund_amount=found.refund_amount,
            refund_reference=found.refund_reference,
            refunded_at=found.refunded_at,
            refunded_by=found.refunded_by,
            items=[_item(item, line) for item, line in lines],
            history=[
                AdminReturnHistoryResponse(
                    old_status=row.old_status,
                    new_status=row.new_status,
                    actor_user_id=row.actor_user_id,
                    created_at=row.created_at,
                )
                for row in history
            ],
            created_at=found.created_at,
            updated_at=found.updated_at,
        )


def _item(item: ReturnItem, line: OrderItem) -> AdminReturnItemResponse:
    return AdminReturnItemResponse(
        order_item_id=item.order_item_id,
        product_id=line.product_id,
        variant_id=line.variant_id,
        product_title=line.product_title,
        sku=line.sku,
        variant_label=line.variant_label,
        quantity=item.quantity,
        accepted_quantity=item.accepted_quantity,
        condition=item.condition,
        refundable=item.refundable,
        refund_amount=item.refund_amount,
        inspection_note=item.inspection_note,
        inventory_movement_id=item.inventory_movement_id,
    )
