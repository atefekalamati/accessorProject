"""Staff return requests: review, receipt and inspection (ORD-09, PRD «مرجوعی» ✓)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ReturnStatus
from app.db.session import get_db_session
from app.modules.auth.dependencies import require_permission
from app.modules.auth.service import CurrentUser
from app.modules.returns.admin_schemas import (
    AdminReturnResponse,
    AdminReturnSummaryResponse,
    InspectReturnRequest,
    RejectReturnRequest,
    ReturnNoteRequest,
)
from app.modules.returns.admin_service import AdminReturnService
from app.modules.returns.router import RETURN_SORTS
from app.shared.idempotency import NO_STORE
from app.shared.pagination import (
    Page,
    PageParams,
    admin_page_params,
    allowed_query_params,
    resolve_sort,
)

router = APIRouter(prefix="/admin/returns", tags=["admin-returns"])

_MANAGE = require_permission("returns:manage")


def get_admin_return_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AdminReturnService:
    return AdminReturnService(session)


def _json(body: AdminReturnResponse) -> JSONResponse:
    return JSONResponse(content=body.model_dump(mode="json"), headers=dict(NO_STORE))


@router.get(
    "",
    response_model=Page[AdminReturnSummaryResponse],
    summary="List return requests by status (page/limit, sort newest|oldest)",
    # Authorization first, so an unauthenticated caller learns nothing from validation.
    dependencies=[
        Depends(_MANAGE),
        Depends(allowed_query_params("page", "limit", "status", "sort")),
    ],
)
async def list_returns(
    paging: Annotated[PageParams, Depends(admin_page_params)],
    service: Annotated[AdminReturnService, Depends(get_admin_return_service)],
    status: ReturnStatus | None = None,
    sort: str | None = None,
) -> JSONResponse:
    order_by = resolve_sort(sort, RETURN_SORTS, default="newest")
    page = await service.list_returns(status=status, order_by=order_by, paging=paging)
    return JSONResponse(content=page.model_dump(mode="json"), headers=dict(NO_STORE))


@router.get(
    "/{return_id}",
    response_model=AdminReturnResponse,
    summary="One return request with inspection fields, staff notes and history",
    dependencies=[Depends(_MANAGE), Depends(allowed_query_params())],
)
async def get_return(
    return_id: UUID,
    service: Annotated[AdminReturnService, Depends(get_admin_return_service)],
) -> JSONResponse:
    return _json(await service.detail(return_id))


@router.post(
    "/{return_id}/approve",
    response_model=AdminReturnResponse,
    summary="Approve a requested return (idempotent)",
)
async def approve_return(
    # Authorization first, then the path, query and body.
    actor: Annotated[CurrentUser, Depends(_MANAGE)],
    _: Annotated[None, Depends(allowed_query_params())],
    return_id: UUID,
    payload: ReturnNoteRequest,
    request: Request,
    service: Annotated[AdminReturnService, Depends(get_admin_return_service)],
) -> JSONResponse:
    return _json(await service.approve(actor, return_id, payload, request))


@router.post(
    "/{return_id}/reject",
    response_model=AdminReturnResponse,
    summary="Reject a requested return with a reason shown to the customer (idempotent)",
)
async def reject_return(
    actor: Annotated[CurrentUser, Depends(_MANAGE)],
    _: Annotated[None, Depends(allowed_query_params())],
    return_id: UUID,
    payload: RejectReturnRequest,
    request: Request,
    service: Annotated[AdminReturnService, Depends(get_admin_return_service)],
) -> JSONResponse:
    return _json(await service.reject(actor, return_id, payload, request))


@router.post(
    "/{return_id}/receive",
    response_model=AdminReturnResponse,
    summary="Mark the returned parcel of an approved request as received (idempotent)",
)
async def receive_return(
    actor: Annotated[CurrentUser, Depends(_MANAGE)],
    _: Annotated[None, Depends(allowed_query_params())],
    return_id: UUID,
    payload: ReturnNoteRequest,
    request: Request,
    service: Annotated[AdminReturnService, Depends(get_admin_return_service)],
) -> JSONResponse:
    return _json(await service.receive(actor, return_id, payload, request))


@router.post(
    "/{return_id}/inspect",
    response_model=AdminReturnResponse,
    summary="Inspect every line of a received return; sellable units go back to stock",
)
async def inspect_return(
    actor: Annotated[CurrentUser, Depends(_MANAGE)],
    _: Annotated[None, Depends(allowed_query_params())],
    return_id: UUID,
    payload: InspectReturnRequest,
    request: Request,
    service: Annotated[AdminReturnService, Depends(get_admin_return_service)],
) -> JSONResponse:
    return _json(await service.inspect(actor, return_id, payload, request))
