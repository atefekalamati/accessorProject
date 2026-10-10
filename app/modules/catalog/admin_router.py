from typing import Annotated, Any, Final
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import UnaryExpression

from app.db.models import Category
from app.modules.auth.dependencies import require_any_permission, require_permission
from app.modules.auth.service import CurrentUser
from app.modules.catalog.admin_schemas import (
    AdminCategoryResponse,
    CreateCategoryRequest,
    UpdateCategoryRequest,
)
from app.modules.catalog.admin_service import MANAGE_PERMISSION, AdminCategoryService
from app.modules.catalog.dependencies import get_admin_category_service
from app.shared.pagination import (
    Page,
    PageParams,
    admin_page_params,
    allowed_query_params,
    resolve_sort,
)

router = APIRouter(prefix="/admin/categories", tags=["admin-categories"])

# Either permission reaches the endpoint; the service limits edit_content to content fields.
_CATEGORY_EDITOR = require_any_permission(MANAGE_PERMISSION, "categories:edit_content")

CATEGORY_SORTS: Final[dict[str, tuple[UnaryExpression[Any], ...]]] = {
    "display_order": (Category.display_order.asc(), Category.id.asc()),
    "newest": (Category.created_at.desc(), Category.id.desc()),
}


@router.get(
    "",
    response_model=Page[AdminCategoryResponse],
    summary="List all non-deleted categories, including inactive ones",
    # Authorization first, so an unauthenticated caller learns nothing from validation.
    dependencies=[
        Depends(_CATEGORY_EDITOR),
        Depends(allowed_query_params("page", "limit", "sort")),
    ],
)
async def list_categories(
    response: Response,
    paging: Annotated[PageParams, Depends(admin_page_params)],
    service: Annotated[AdminCategoryService, Depends(get_admin_category_service)],
    sort: str | None = None,
) -> Page[AdminCategoryResponse]:
    order_by = resolve_sort(sort, CATEGORY_SORTS, default="display_order")
    response.headers["Cache-Control"] = "no-store"
    return await service.list_categories(order_by, paging)


@router.post(
    "",
    response_model=AdminCategoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a category",
)
async def create_category(
    payload: CreateCategoryRequest,
    request: Request,
    response: Response,
    actor: Annotated[CurrentUser, Depends(require_permission(MANAGE_PERMISSION))],
    service: Annotated[AdminCategoryService, Depends(get_admin_category_service)],
) -> AdminCategoryResponse:
    response.headers["Cache-Control"] = "no-store"
    return await service.create(actor, payload, request)


@router.patch(
    "/{category_id}",
    response_model=AdminCategoryResponse,
    summary="Update a category; structural fields need catalog:manage",
)
async def update_category(
    category_id: UUID,
    payload: UpdateCategoryRequest,
    request: Request,
    response: Response,
    actor: Annotated[CurrentUser, Depends(_CATEGORY_EDITOR)],
    service: Annotated[AdminCategoryService, Depends(get_admin_category_service)],
) -> AdminCategoryResponse:
    response.headers["Cache-Control"] = "no-store"
    return await service.update(actor, category_id, payload, request)


@router.delete(
    "/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft delete a category without sub-categories or products",
)
async def delete_category(
    category_id: UUID,
    request: Request,
    actor: Annotated[CurrentUser, Depends(require_permission(MANAGE_PERMISSION))],
    service: Annotated[AdminCategoryService, Depends(get_admin_category_service)],
) -> Response:
    await service.delete(actor, category_id, request)
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers={"Cache-Control": "no-store"})
