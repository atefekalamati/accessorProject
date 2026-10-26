from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.service import CurrentUser
from app.modules.orders.schemas import CreateOrderRequest, OrderResponse, OrderStatusResponse
from app.modules.orders.service import OrderService
from app.shared.idempotency import NO_STORE, idempotency_key
from app.shared.pagination import allowed_query_params

router = APIRouter(prefix="/orders", tags=["orders"])


def get_order_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> OrderService:
    return OrderService(session)


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
