from typing import Annotated, Any, Final
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import UnaryExpression

from app.db.models import User, UserStatus
from app.modules.admin.dependencies import get_admin_user_service
from app.modules.admin.repository import UserFilters
from app.modules.admin.schemas import (
    ASSIGNABLE_ROLES,
    AdminUserResponse,
    UpdateUserRolesRequest,
    UpdateUserStatusRequest,
)
from app.modules.admin.service import AdminUserService
from app.modules.auth.dependencies import require_permission
from app.modules.auth.service import CurrentUser
from app.shared.pagination import (
    Page,
    PageParams,
    admin_page_params,
    allowed_query_params,
    resolve_sort,
)
from app.shared.search import invalid_query, mobile_digits

router = APIRouter(prefix="/admin/users", tags=["admin-users"])

USER_SORTS: Final[dict[str, tuple[UnaryExpression[Any], ...]]] = {
    "newest": (User.created_at.desc(), User.id.desc()),
    "oldest": (User.created_at.asc(), User.id.asc()),
}


@router.get(
    "",
    response_model=Page[AdminUserResponse],
    summary="List users with page/limit pagination and mobile, status and role filters",
    # Authorization first, so an unauthenticated caller learns nothing from validation.
    dependencies=[
        Depends(require_permission("users:read")),
        Depends(allowed_query_params("page", "limit", "mobile", "status", "role", "sort")),
    ],
)
async def list_users(
    response: Response,
    paging: Annotated[PageParams, Depends(admin_page_params)],
    service: Annotated[AdminUserService, Depends(get_admin_user_service)],
    mobile: Annotated[str | None, Query(max_length=17)] = None,
    status: UserStatus | None = None,
    role: str | None = None,
    sort: str | None = None,
) -> Page[AdminUserResponse]:
    if role is not None and role not in ASSIGNABLE_ROLES:
        raise invalid_query("role", f"Allowed values: {', '.join(sorted(ASSIGNABLE_ROLES))}")
    order_by = resolve_sort(sort, USER_SORTS, default="newest")
    filters = UserFilters(mobile_digits=mobile_digits(mobile), status=status, role=role)
    response.headers["Cache-Control"] = "no-store"
    return await service.list_users(filters, order_by, paging)


@router.patch(
    "/{user_id}/status",
    response_model=AdminUserResponse,
    summary="Activate, deactivate or block a user; leaving active revokes all sessions",
)
async def change_status(
    user_id: UUID,
    payload: UpdateUserStatusRequest,
    request: Request,
    response: Response,
    actor: Annotated[CurrentUser, Depends(require_permission("users:manage"))],
    service: Annotated[AdminUserService, Depends(get_admin_user_service)],
) -> AdminUserResponse:
    response.headers["Cache-Control"] = "no-store"
    return await service.change_status(actor, user_id, payload.status, request)


@router.patch(
    "/{user_id}/role",
    response_model=AdminUserResponse,
    summary="Replace a user's roles (super admin only)",
)
async def change_roles(
    user_id: UUID,
    payload: UpdateUserRolesRequest,
    request: Request,
    response: Response,
    actor: Annotated[CurrentUser, Depends(require_permission("users:manage_roles"))],
    service: Annotated[AdminUserService, Depends(get_admin_user_service)],
) -> AdminUserResponse:
    response.headers["Cache-Control"] = "no-store"
    return await service.change_roles(actor, user_id, payload.roles, request)
