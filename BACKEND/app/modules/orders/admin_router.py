"""Admin orders and payments: lists and detail (ADM-01, PRD «مدیریت سفارش» ✓)."""

from __future__ import annotations

import re
from typing import Annotated, Any, Final
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import UnaryExpression

from app.db.models import OrderStatus, Payment, PaymentStatus, ShipmentStatus
from app.db.models.orders import Order
from app.db.session import get_db_session
from app.modules.auth.dependencies import require_permission
from app.modules.orders.admin import AdminOrderService, OrderFilters, PaymentFilters
from app.modules.orders.admin_schemas import (
    AdminOrderDetailResponse,
    AdminOrderSummaryResponse,
    AdminPaymentResponse,
)
from app.shared.idempotency import NO_STORE
from app.shared.pagination import (
    Page,
    PageParams,
    admin_page_params,
    allowed_query_params,
    resolve_sort,
)
from app.shared.search import TimeRange, invalid_query, is_mobile_search, mobile_digits, time_range

orders_router = APIRouter(prefix="/admin/orders", tags=["admin-orders"])
payments_router = APIRouter(prefix="/admin/payments", tags=["admin-orders"])

ORDER_SORTS: Final[dict[str, tuple[UnaryExpression[Any], ...]]] = {
    "newest": (Order.created_at.desc(),),
    "oldest": (Order.created_at.asc(),),
}
PAYMENT_SORTS: Final[dict[str, tuple[UnaryExpression[Any], ...]]] = {
    "newest": (Payment.created_at.desc(),),
    "oldest": (Payment.created_at.asc(),),
}
# An order number or its prefix: "ORD", "ORD-2026", "ORD-2026-0000" (case-insensitive).
_NUMBER_PREFIX: Final = re.compile(r"ORD(-\d{0,4}(-\d{0,12})?)?", re.IGNORECASE)
_READ = Depends(require_permission("orders:read"))


def get_admin_order_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AdminOrderService:
    return AdminOrderService(session)


def _search(q: str | None) -> tuple[str | None, str | None]:
    """``q`` as (order number prefix, mobile digits); anything else is 400."""
    if q is None or q.strip() == "":
        return None, None
    q = q.strip()
    if _NUMBER_PREFIX.fullmatch(q):
        return q.upper(), None
    if is_mobile_search(q):
        return None, mobile_digits(q, field="q")
    raise invalid_query("q", "Must be an order number (prefix) or 3-16 mobile digits")


@orders_router.get(
    "",
    response_model=Page[AdminOrderSummaryResponse],
    summary="List orders by status, payment, shipment, number or mobile, and date",
    # Authorization first, so an unauthenticated caller learns nothing from validation.
    dependencies=[
        _READ,
        Depends(
            allowed_query_params(
                "page",
                "limit",
                "status",
                "payment_status",
                "shipment_status",
                "q",
                "from",
                "to",
                "sort",
            )
        ),
    ],
)
async def list_orders(
    paging: Annotated[PageParams, Depends(admin_page_params)],
    created: Annotated[TimeRange, Depends(time_range)],
    service: Annotated[AdminOrderService, Depends(get_admin_order_service)],
    status: OrderStatus | None = None,
    payment_status: PaymentStatus | None = None,
    shipment_status: ShipmentStatus | None = None,
    q: Annotated[str | None, Query(max_length=40)] = None,
    sort: str | None = None,
) -> JSONResponse:
    order_by = resolve_sort(sort, ORDER_SORTS, default="newest")
    number_prefix, digits = _search(q)
    filters = OrderFilters(
        status=status,
        payment_status=payment_status,
        shipment_status=shipment_status,
        number_prefix=number_prefix,
        mobile_digits=digits,
        created=created,
    )
    page = await service.list_orders(filters, order_by, paging)
    return JSONResponse(content=page.model_dump(mode="json"), headers=dict(NO_STORE))


@orders_router.get(
    "/{order_id}",
    response_model=AdminOrderDetailResponse,
    summary="One order with its lines, snapshots, payments and status history",
    dependencies=[_READ, Depends(allowed_query_params())],
)
async def get_order(
    order_id: UUID,
    service: Annotated[AdminOrderService, Depends(get_admin_order_service)],
) -> JSONResponse:
    detail = await service.detail(order_id)
    return JSONResponse(content=detail.model_dump(mode="json"), headers=dict(NO_STORE))


@payments_router.get(
    "",
    response_model=Page[AdminPaymentResponse],
    summary="List payments by status (e.g. refund_required), failure reason and date",
    dependencies=[
        _READ,
        Depends(
            allowed_query_params("page", "limit", "status", "failure_reason", "from", "to", "sort")
        ),
    ],
)
async def list_payments(
    paging: Annotated[PageParams, Depends(admin_page_params)],
    created: Annotated[TimeRange, Depends(time_range)],
    service: Annotated[AdminOrderService, Depends(get_admin_order_service)],
    status: PaymentStatus | None = None,
    failure_reason: Annotated[str | None, Query(min_length=1, max_length=40)] = None,
    sort: str | None = None,
) -> JSONResponse:
    order_by = resolve_sort(sort, PAYMENT_SORTS, default="newest")
    filters = PaymentFilters(status=status, failure_reason=failure_reason, created=created)
    page = await service.list_payments(filters, order_by, paging)
    return JSONResponse(content=page.model_dump(mode="json"), headers=dict(NO_STORE))
