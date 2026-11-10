import re
from typing import Annotated, Final
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.db.models import PageStatus
from app.db.models.catalog import SLUG_PATTERN
from app.db.session import get_db_session
from app.modules.auth.dependencies import require_permission
from app.modules.auth.service import CurrentUser
from app.modules.content.faq import FaqService
from app.modules.content.pages import PageFilters, PageService
from app.modules.content.schemas import (
    AdminFaqResponse,
    AdminPageResponse,
    CreateFaqRequest,
    CreatePageRequest,
    PublicFaqResponse,
    PublicPageResponse,
    UpdateFaqRequest,
    UpdatePageRequest,
)
from app.shared.pagination import Page, PageParams, admin_page_params, allowed_query_params

pages_router = APIRouter(prefix="/pages", tags=["content"])
admin_pages_router = APIRouter(prefix="/admin/pages", tags=["admin-content"])
faq_router = APIRouter(prefix="/faq", tags=["content"])
admin_faq_router = APIRouter(prefix="/admin/faq", tags=["admin-content"])

_MANAGER = require_permission("content:manage")
Manager = Annotated[CurrentUser, Depends(_MANAGER)]
_NO_STORE: Final = {"Cache-Control": "no-store"}
_SLUG: Final = re.compile(SLUG_PATTERN)


def get_page_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PageService:
    return PageService(session)


Pages = Annotated[PageService, Depends(get_page_service)]


@pages_router.get("/{slug}", response_model=PublicPageResponse, summary="A published static page")
async def get_page(slug: str, service: Pages) -> PublicPageResponse:
    if _SLUG.fullmatch(slug) is None:  # cannot match any page: answered like an unknown one
        raise NotFoundError(message="Page not found")
    return await service.public(slug)


@admin_pages_router.get(
    "",
    response_model=Page[AdminPageResponse],
    summary="Live static pages, drafts included, by slug",
    dependencies=[Depends(_MANAGER), Depends(allowed_query_params("page", "limit", "status"))],
)
async def list_pages(
    response: Response,
    paging: Annotated[PageParams, Depends(admin_page_params)],
    service: Pages,
    page_status: Annotated[PageStatus | None, Query(alias="status")] = None,
) -> Page[AdminPageResponse]:
    response.headers.update(_NO_STORE)
    return await service.list_pages(PageFilters(status=page_status), paging)


@admin_pages_router.post(
    "",
    response_model=AdminPageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a static page (Markdown without raw HTML)",
)
async def create_page(
    payload: CreatePageRequest,
    request: Request,
    response: Response,
    actor: Manager,
    service: Pages,
) -> AdminPageResponse:
    response.headers.update(_NO_STORE)
    return await service.create(actor, payload, request)


@admin_pages_router.patch(
    "/{page_id}",
    response_model=AdminPageResponse,
    summary="Change a static page; its slug is fixed",
)
async def update_page(
    page_id: UUID,
    payload: UpdatePageRequest,
    request: Request,
    response: Response,
    actor: Manager,
    service: Pages,
) -> AdminPageResponse:
    response.headers.update(_NO_STORE)
    return await service.update(actor, page_id, payload, request)


@admin_pages_router.delete(
    "/{page_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft delete a static page; its slug becomes free",
)
async def delete_page(page_id: UUID, request: Request, actor: Manager, service: Pages) -> Response:
    await service.delete(actor, page_id, request)
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=_NO_STORE)


# --- FAQ (CNT-05) ------------------------------------------------------------------------


def get_faq_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> FaqService:
    return FaqService(session)


Faq = Annotated[FaqService, Depends(get_faq_service)]


@faq_router.get(
    "",
    response_model=PublicFaqResponse,
    summary="Published questions, grouped, in display order",
)
async def get_faq(service: Faq) -> PublicFaqResponse:
    return await service.public()


@admin_faq_router.get(
    "",
    response_model=Page[AdminFaqResponse],
    summary="Live FAQ items, unpublished included, in display order",
    dependencies=[Depends(_MANAGER), Depends(allowed_query_params("page", "limit"))],
)
async def list_faq(
    response: Response,
    paging: Annotated[PageParams, Depends(admin_page_params)],
    service: Faq,
) -> Page[AdminFaqResponse]:
    response.headers.update(_NO_STORE)
    return await service.list_items(paging)


@admin_faq_router.post(
    "",
    response_model=AdminFaqResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a FAQ item (answer in Markdown without raw HTML)",
)
async def create_faq(
    payload: CreateFaqRequest,
    request: Request,
    response: Response,
    actor: Manager,
    service: Faq,
) -> AdminFaqResponse:
    response.headers.update(_NO_STORE)
    return await service.create(actor, payload, request)


@admin_faq_router.patch("/{item_id}", response_model=AdminFaqResponse, summary="Change a FAQ item")
async def update_faq(
    item_id: UUID,
    payload: UpdateFaqRequest,
    request: Request,
    response: Response,
    actor: Manager,
    service: Faq,
) -> AdminFaqResponse:
    response.headers.update(_NO_STORE)
    return await service.update(actor, item_id, payload, request)


@admin_faq_router.delete(
    "/{item_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Soft delete a FAQ item"
)
async def delete_faq(item_id: UUID, request: Request, actor: Manager, service: Faq) -> Response:
    await service.delete(actor, item_id, request)
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=_NO_STORE)
