from typing import Annotated, Final
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BadRequestError
from app.db.session import get_db_session
from app.modules.auth.dependencies import require_permission
from app.modules.auth.service import CurrentUser
from app.modules.shipping.admin_schemas import (
    AdminShippingMethodResponse,
    CreateShippingMethodRequest,
    UpdateShippingMethodRequest,
)
from app.modules.shipping.admin_service import (
    MANAGE_PERMISSION,
    STATES,
    AdminShippingService,
    ShippingMethodFilters,
)
from app.shared.pagination import Page, PageParams, admin_page_params, allowed_query_params

router = APIRouter(prefix="/admin/shipping-methods", tags=["admin-shipping"])

_MANAGER = require_permission(MANAGE_PERMISSION)
Manager = Annotated[CurrentUser, Depends(_MANAGER)]
_NO_STORE: Final = {"Cache-Control": "no-store"}


def get_admin_shipping_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AdminShippingService:
    return AdminShippingService(session)


Service = Annotated[AdminShippingService, Depends(get_admin_shipping_service)]


def _invalid_query(field: str, message: str, type_: str) -> BadRequestError:
    return BadRequestError(
        message="Request validation failed",
        details=[{"field": f"query.{field}", "message": message, "type": type_}],
    )


@router.get(
    "",
    response_model=Page[AdminShippingMethodResponse],
    summary="Live shipping methods, inactive ones included, in display order",
    dependencies=[
        Depends(_MANAGER),
        Depends(allowed_query_params("page", "limit", "q", "state")),
    ],
)
async def list_shipping_methods(
    response: Response,
    paging: Annotated[PageParams, Depends(admin_page_params)],
    service: Service,
    q: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    state: str | None = None,
) -> Page[AdminShippingMethodResponse]:
    search = None if q is None else q.strip()
    if search == "":
        raise _invalid_query("q", "Must not be blank", "value_error")
    if state is not None and state not in STATES:
        raise _invalid_query("state", f"One of {', '.join(STATES)}", "enum")
    response.headers.update(_NO_STORE)
    return await service.list_methods(ShippingMethodFilters(q=search, state=state), paging)


@router.get("/{method_id}", response_model=AdminShippingMethodResponse)
async def get_shipping_method(
    method_id: UUID, response: Response, _actor: Manager, service: Service
) -> AdminShippingMethodResponse:
    response.headers.update(_NO_STORE)
    return await service.get(method_id)


@router.post(
    "",
    response_model=AdminShippingMethodResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a shipping method (cost and threshold in Toman)",
)
async def create_shipping_method(
    payload: CreateShippingMethodRequest,
    request: Request,
    response: Response,
    actor: Manager,
    service: Service,
) -> AdminShippingMethodResponse:
    response.headers.update(_NO_STORE)
    return await service.create(actor, payload, request)


@router.patch(
    "/{method_id}",
    response_model=AdminShippingMethodResponse,
    summary="Change a shipping method; affects later orders only",
)
async def update_shipping_method(
    method_id: UUID,
    payload: UpdateShippingMethodRequest,
    request: Request,
    response: Response,
    actor: Manager,
    service: Service,
) -> AdminShippingMethodResponse:
    response.headers.update(_NO_STORE)
    return await service.update(actor, method_id, payload, request)


@router.delete(
    "/{method_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft delete a shipping method; orders keep their snapshot",
)
async def delete_shipping_method(
    method_id: UUID, request: Request, actor: Manager, service: Service
) -> Response:
    await service.delete(actor, method_id, request)
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=_NO_STORE)
