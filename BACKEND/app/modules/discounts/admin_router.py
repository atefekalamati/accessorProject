from typing import Annotated, Any, Final
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy import UnaryExpression
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BadRequestError
from app.db.models import DiscountCode
from app.db.session import get_db_session
from app.modules.auth.dependencies import require_permission
from app.modules.auth.service import CurrentUser
from app.modules.discounts.admin_schemas import (
    CreateDiscountRequest,
    DiscountResponse,
    UpdateDiscountRequest,
)
from app.modules.discounts.admin_service import (
    MANAGE_PERMISSION,
    STATES,
    AdminDiscountService,
    DiscountFilters,
)
from app.shared.pagination import (
    Page,
    PageParams,
    admin_page_params,
    allowed_query_params,
    resolve_sort,
)

router = APIRouter(prefix="/admin/discounts", tags=["admin-discounts"])

_MANAGER = require_permission(MANAGE_PERMISSION)
Manager = Annotated[CurrentUser, Depends(_MANAGER)]
_NO_STORE: Final = {"Cache-Control": "no-store"}
SORTS: Final[dict[str, tuple[UnaryExpression[Any], ...]]] = {
    "newest": (DiscountCode.created_at.desc(),),
    "code": (DiscountCode.code.asc(),),
}


def get_admin_discount_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AdminDiscountService:
    return AdminDiscountService(session)


Service = Annotated[AdminDiscountService, Depends(get_admin_discount_service)]


@router.get(
    "",
    response_model=Page[DiscountResponse],
    summary="Live discount codes with their use counts",
    dependencies=[
        Depends(_MANAGER),
        Depends(allowed_query_params("page", "limit", "q", "state", "sort")),
    ],
)
async def list_discounts(
    response: Response,
    paging: Annotated[PageParams, Depends(admin_page_params)],
    service: Service,
    q: Annotated[str | None, Query(min_length=1, max_length=32)] = None,
    state: str | None = None,
    sort: str | None = None,
) -> Page[DiscountResponse]:
    search = None if q is None else q.strip()
    if search == "":
        raise BadRequestError(
            message="Request validation failed",
            details=[{"field": "query.q", "message": "Must not be blank", "type": "value_error"}],
        )
    if state is not None and state not in STATES:
        raise BadRequestError(
            message="Request validation failed",
            details=[
                {"field": "query.state", "message": f"One of {', '.join(STATES)}", "type": "enum"}
            ],
        )
    order_by = resolve_sort(sort, SORTS, default="newest")
    response.headers.update(_NO_STORE)
    return await service.list_codes(DiscountFilters(q=search, state=state), order_by, paging)


@router.get("/{code_id}", response_model=DiscountResponse)
async def get_discount(
    code_id: UUID, response: Response, _actor: Manager, service: Service
) -> DiscountResponse:
    response.headers.update(_NO_STORE)
    return await service.get(code_id)


@router.post(
    "",
    response_model=DiscountResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a discount code (percent in basis points, fixed in Toman)",
)
async def create_discount(
    payload: CreateDiscountRequest,
    request: Request,
    response: Response,
    actor: Manager,
    service: Service,
) -> DiscountResponse:
    response.headers.update(_NO_STORE)
    return await service.create(actor, payload, request)


@router.patch(
    "/{code_id}",
    response_model=DiscountResponse,
    summary="Change a code's rules; affects later orders only",
)
async def update_discount(
    code_id: UUID,
    payload: UpdateDiscountRequest,
    request: Request,
    response: Response,
    actor: Manager,
    service: Service,
) -> DiscountResponse:
    response.headers.update(_NO_STORE)
    return await service.update(actor, code_id, payload, request)


@router.delete("/{code_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_discount(
    code_id: UUID, request: Request, actor: Manager, service: Service
) -> Response:
    await service.delete(actor, code_id, request)
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=_NO_STORE)
