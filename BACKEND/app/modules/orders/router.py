from typing import Annotated, Any, Final
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import UnaryExpression

from app.core.config import Settings, get_app_settings
from app.db.models import Order, OrderStatus
from app.db.models.orders import ORDER_NUMBER_PATTERN
from app.db.session import get_db_session
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.service import CurrentUser
from app.modules.orders.account import AccountOrderService
from app.modules.orders.schemas import (
    CreateOrderRequest,
    OrderDetailResponse,
    OrderResponse,
    OrderStatusResponse,
    OrderSummaryResponse,
)
from app.modules.orders.service import OrderService
from app.shared.idempotency import NO_STORE, idempotency_key
from app.shared.pagination import (
    Page,
    PageParams,
    admin_page_params,
    allowed_query_params,
    resolve_sort,
)
from app.shared.storage import FileStorage, get_file_storage

router = APIRouter(prefix="/orders", tags=["orders"])


def get_order_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> OrderService:
    return OrderService(session)


def get_account_order_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    storage: Annotated[FileStorage, Depends(get_file_storage)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> AccountOrderService:
    return AccountOrderService(session, storage, return_window_days=settings.return_window_days)


ORDER_SORTS: Final[dict[str, tuple[UnaryExpression[Any], ...]]] = {
    "newest": (Order.created_at.desc(),),
    "oldest": (Order.created_at.asc(),),
}


@router.get(
    "",
    response_model=Page[OrderSummaryResponse],
    summary="List your own orders, newest first (page/limit, status, sort)",
)
async def list_orders(
    # Authentication first: a bad query never answers before 401.
    user: Annotated[CurrentUser, Depends(get_current_user)],
    _: Annotated[None, Depends(allowed_query_params("page", "limit", "status", "sort"))],
    paging: Annotated[PageParams, Depends(admin_page_params)],
    service: Annotated[AccountOrderService, Depends(get_account_order_service)],
    status: OrderStatus | None = None,
    sort: str | None = None,
) -> JSONResponse:
    order_by = resolve_sort(sort, ORDER_SORTS, default="newest")
    page = await service.list_orders(user.id, status=status, order_by=order_by, paging=paging)
    return JSONResponse(content=page.model_dump(mode="json"), headers=dict(NO_STORE))


@router.get(
    "/{order_number}",
    response_model=OrderDetailResponse,
    summary="One of your orders with its payments, history and what you can do now",
)
async def get_order(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    _: Annotated[None, Depends(allowed_query_params())],
    order_number: Annotated[str, Path(pattern=ORDER_NUMBER_PATTERN)],
    service: Annotated[AccountOrderService, Depends(get_account_order_service)],
) -> JSONResponse:
    detail = await service.detail(user.id, order_number)
    return JSONResponse(content=detail.model_dump(mode="json"), headers=dict(NO_STORE))


@router.post(
    "",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Place an order from the cart: reserve stock for 15 minutes (Idempotency-Key)",
)
async def create_order(
    payload: CreateOrderRequest,
    request: Request,
    # Authentication first, then the query and the header (ADR-046): neither answers
    # before 401.
    user: Annotated[CurrentUser, Depends(get_current_user)],
    _: Annotated[None, Depends(allowed_query_params())],
    key: Annotated[str, Depends(idempotency_key)],
    service: Annotated[OrderService, Depends(get_order_service)],
) -> JSONResponse:
    placed = await service.place(user.id, key, payload, request)
    return JSONResponse(status_code=placed.status_code, content=placed.body, headers=dict(NO_STORE))


@router.post(
    "/{order_id}/cancel",
    response_model=OrderStatusResponse,
    summary="Cancel your unpaid order: free its stock and discount code use",
)
async def cancel_order(
    # Authentication first: a bad path or query never answers before 401.
    user: Annotated[CurrentUser, Depends(get_current_user)],
    _: Annotated[None, Depends(allowed_query_params())],
    order_id: UUID,
    request: Request,
    service: Annotated[OrderService, Depends(get_order_service)],
) -> JSONResponse:
    cancelled = await service.cancel(user.id, order_id, request)
    return JSONResponse(content=cancelled.model_dump(mode="json"), headers=dict(NO_STORE))
