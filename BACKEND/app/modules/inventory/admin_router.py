from typing import Annotated, Final
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response

from app.core.errors import BadRequestError
from app.db.models import ReservationStatus
from app.modules.auth.dependencies import require_any_permission, require_permission
from app.modules.auth.service import CurrentUser
from app.modules.inventory.admin_repository import InventoryFilters
from app.modules.inventory.admin_schemas import (
    InventoryRow,
    MovementRow,
    ReservationRow,
    UpdateInventoryRequest,
)
from app.modules.inventory.admin_service import (
    READ_PERMISSIONS,
    UPDATE_PERMISSION,
    AdminInventoryService,
)
from app.modules.inventory.dependencies import get_admin_inventory_service
from app.modules.inventory.stock import StockStatus
from app.shared.pagination import (
    Page,
    PageParams,
    admin_page_params,
    allowed_query_params,
    resolve_sort,
)

router = APIRouter(prefix="/admin/inventory", tags=["admin-inventory"])

_READER = require_any_permission(*READ_PERMISSIONS)
_EDITOR = require_permission(UPDATE_PERMISSION)
Service = Annotated[AdminInventoryService, Depends(get_admin_inventory_service)]
_NO_STORE: Final = {"Cache-Control": "no-store"}
STOCK_SORTS: Final = {name: name for name in ("sku", "free_asc", "free_desc", "updated")}


@router.get(
    "",
    response_model=Page[InventoryRow],
    summary="Stock of every non-deleted variant, filterable by low or out of stock",
    # Authorization first, so an unauthenticated caller learns nothing from validation.
    dependencies=[
        Depends(_READER),
        Depends(allowed_query_params("page", "limit", "q", "product_id", "stock_status", "sort")),
    ],
)
async def list_inventory(
    response: Response,
    paging: Annotated[PageParams, Depends(admin_page_params)],
    service: Service,
    q: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    product_id: UUID | None = None,
    stock_status: StockStatus | None = None,
    sort: str | None = None,
) -> Page[InventoryRow]:
    search = None if q is None else q.strip()
    if search == "":
        raise BadRequestError(
            message="Request validation failed",
            details=[{"field": "query.q", "message": "Must not be blank", "type": "value_error"}],
        )
    order = resolve_sort(sort, STOCK_SORTS, default="sku")
    filters = InventoryFilters(q=search, product_id=product_id, stock_status=stock_status)
    response.headers.update(_NO_STORE)
    return await service.list_stock(filters, order, paging)


@router.get(
    "/reservations",
    response_model=Page[ReservationRow],
    summary="Reservations, newest first; an active one past its expiry shows as expired",
    dependencies=[
        Depends(_READER),
        Depends(allowed_query_params("page", "limit", "status", "order_id", "variant_id")),
    ],
)
async def list_reservations(
    response: Response,
    paging: Annotated[PageParams, Depends(admin_page_params)],
    service: Service,
    status: ReservationStatus | None = None,
    order_id: UUID | None = None,
    variant_id: UUID | None = None,
) -> Page[ReservationRow]:
    response.headers.update(_NO_STORE)
    return await service.reservations(
        status=status, order_id=order_id, variant_id=variant_id, params=paging
    )


@router.patch(
    "/{variant_id}",
    response_model=InventoryRow,
    summary="Adjust a variant's stock and/or its low-stock threshold (reason required)",
)
async def update_inventory(
    variant_id: UUID,
    payload: UpdateInventoryRequest,
    request: Request,
    response: Response,
    actor: Annotated[CurrentUser, Depends(_EDITOR)],
    service: Service,
) -> InventoryRow:
    response.headers.update(_NO_STORE)
    return await service.update(actor, variant_id, payload, request)


@router.get(
    "/{variant_id}/history",
    response_model=Page[MovementRow],
    summary="Stock movements of a variant, newest first",
    dependencies=[Depends(_READER), Depends(allowed_query_params("page", "limit"))],
)
async def get_inventory_history(
    variant_id: UUID,
    response: Response,
    paging: Annotated[PageParams, Depends(admin_page_params)],
    service: Service,
) -> Page[MovementRow]:
    response.headers.update(_NO_STORE)
    return await service.history(variant_id, paging)
