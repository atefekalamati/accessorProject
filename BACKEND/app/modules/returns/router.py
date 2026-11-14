"""Customer return requests (ORD-08, PRD «مرجوعی» ✓, ADR-063)."""

from __future__ import annotations

from typing import Annotated, Any, Final
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import UnaryExpression

from app.core.config import Settings, get_app_settings
from app.db.models import ReturnRequest, ReturnStatus
from app.db.models.orders import ORDER_NUMBER_PATTERN
from app.db.session import get_db_session
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.service import CurrentUser
from app.modules.returns.schemas import (
    CreateReturnRequest,
    ReturnResponse,
    ReturnSummaryResponse,
)
from app.modules.returns.service import ReturnService
from app.shared.idempotency import NO_STORE, idempotency_key
from app.shared.pagination import (
    Page,
    PageParams,
    admin_page_params,
    allowed_query_params,
    resolve_sort,
)

router = APIRouter(tags=["returns"])

RETURN_SORTS: Final[dict[str, tuple[UnaryExpression[Any], ...]]] = {
    "newest": (ReturnRequest.created_at.desc(),),
    "oldest": (ReturnRequest.created_at.asc(),),
}


def get_return_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> ReturnService:
    return ReturnService(session, window_days=settings.return_window_days)


@router.post(
    "/orders/{order_number}/returns",
    response_model=ReturnResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ask to return lines of your delivered order (Idempotency-Key)",
)
async def create_return(
    payload: CreateReturnRequest,
    request: Request,
    # Authentication first, then the query and the header: neither answers before 401.
    user: Annotated[CurrentUser, Depends(get_current_user)],
    _: Annotated[None, Depends(allowed_query_params())],
    key: Annotated[str, Depends(idempotency_key)],
    order_number: Annotated[str, Path(pattern=ORDER_NUMBER_PATTERN)],
    service: Annotated[ReturnService, Depends(get_return_service)],
) -> JSONResponse:
    created = await service.create(user.id, order_number, key, payload, request)
    return JSONResponse(
        status_code=created.status_code, content=created.body, headers=dict(NO_STORE)
    )


@router.get(
    "/returns",
    response_model=Page[ReturnSummaryResponse],
    summary="List your own return requests (page/limit, status, sort)",
)
async def list_returns(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    _: Annotated[None, Depends(allowed_query_params("page", "limit", "status", "sort"))],
    paging: Annotated[PageParams, Depends(admin_page_params)],
    service: Annotated[ReturnService, Depends(get_return_service)],
    status: ReturnStatus | None = None,
    sort: str | None = None,
) -> JSONResponse:
    order_by = resolve_sort(sort, RETURN_SORTS, default="newest")
    page = await service.list_returns(user.id, status=status, order_by=order_by, paging=paging)
    return JSONResponse(content=page.model_dump(mode="json"), headers=dict(NO_STORE))


@router.get(
    "/returns/{return_id}",
    response_model=ReturnResponse,
    summary="One of your return requests with its items and history",
)
async def get_return(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    _: Annotated[None, Depends(allowed_query_params())],
    return_id: UUID,
    service: Annotated[ReturnService, Depends(get_return_service)],
) -> JSONResponse:
    found = await service.detail(user.id, return_id)
    return JSONResponse(content=found.model_dump(mode="json"), headers=dict(NO_STORE))


@router.post(
    "/returns/{return_id}/cancel",
    response_model=ReturnResponse,
    summary="Cancel your return request while it is still requested",
)
async def cancel_return(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    _: Annotated[None, Depends(allowed_query_params())],
    return_id: UUID,
    request: Request,
    service: Annotated[ReturnService, Depends(get_return_service)],
) -> JSONResponse:
    cancelled = await service.cancel(user.id, return_id, request)
    return JSONResponse(content=cancelled.model_dump(mode="json"), headers=dict(NO_STORE))
