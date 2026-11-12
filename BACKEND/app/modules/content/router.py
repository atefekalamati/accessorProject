import re
from typing import Annotated, Final
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_app_settings
from app.core.errors import NotFoundError
from app.db.models import ContactStatus, PageStatus
from app.db.models.catalog import SLUG_PATTERN
from app.db.session import get_db_session
from app.modules.auth.dependencies import get_optional_user, require_permission
from app.modules.auth.service import CurrentUser
from app.modules.catalog.dependencies import get_product_service
from app.modules.catalog.product_service import ProductService
from app.modules.catalog.repository import CategoryRepository
from app.modules.content.banners import BannerService
from app.modules.content.contact import ContactFilters, ContactService
from app.modules.content.faq import FaqService
from app.modules.content.home import HomeService
from app.modules.content.home_admin import AdminHomeService
from app.modules.content.pages import PageFilters, PageService
from app.modules.content.schemas import (
    AdminBannerResponse,
    AdminContactDetail,
    AdminContactSummary,
    AdminFaqResponse,
    AdminPageResponse,
    AdminSectionResponse,
    ContactRequest,
    CreateBannerRequest,
    CreateFaqRequest,
    CreatePageRequest,
    CreateSectionRequest,
    HomeResponse,
    PublicFaqResponse,
    PublicPageResponse,
    UpdateBannerRequest,
    UpdateContactRequest,
    UpdateFaqRequest,
    UpdatePageRequest,
    UpdateSectionRequest,
)
from app.shared.audit import client_ip
from app.shared.pagination import Page, PageParams, admin_page_params, allowed_query_params
from app.shared.storage import FileStorage, get_file_storage

pages_router = APIRouter(prefix="/pages", tags=["content"])
admin_pages_router = APIRouter(prefix="/admin/pages", tags=["admin-content"])
faq_router = APIRouter(prefix="/faq", tags=["content"])
admin_faq_router = APIRouter(prefix="/admin/faq", tags=["admin-content"])
contact_router = APIRouter(prefix="/contact", tags=["content"])
home_router = APIRouter(prefix="/home", tags=["content"])
admin_banners_router = APIRouter(prefix="/admin/banners", tags=["admin-content"])
admin_home_router = APIRouter(prefix="/admin/home/sections", tags=["admin-content"])
admin_contact_router = APIRouter(prefix="/admin/contact-messages", tags=["admin-content"])

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


# --- contact form (CNT-06) ----------------------------------------------------------------


def get_contact_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> ContactService:
    return ContactService(session, settings)


Contact = Annotated[ContactService, Depends(get_contact_service)]
_CONTACT_MANAGER = require_permission("contact_messages:manage")
ContactManager = Annotated[CurrentUser, Depends(_CONTACT_MANAGER)]


@contact_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Send a message to the store; limited per IP and per mobile (429)",
)
async def submit_contact(
    payload: ContactRequest,
    request: Request,
    user: Annotated[CurrentUser | None, Depends(get_optional_user)],
    service: Contact,
) -> Response:
    await service.submit(payload, user_id=None if user is None else user.id, ip=client_ip(request))
    return Response(status_code=status.HTTP_201_CREATED, headers=_NO_STORE)


@admin_contact_router.get(
    "",
    response_model=Page[AdminContactSummary],
    summary="Contact messages, newest first, optionally by status",
    dependencies=[
        Depends(_CONTACT_MANAGER),
        Depends(allowed_query_params("page", "limit", "status")),
    ],
)
async def list_contact_messages(
    response: Response,
    paging: Annotated[PageParams, Depends(admin_page_params)],
    service: Contact,
    message_status: Annotated[ContactStatus | None, Query(alias="status")] = None,
) -> Page[AdminContactSummary]:
    response.headers.update(_NO_STORE)
    return await service.list_messages(ContactFilters(status=message_status), paging)


@admin_contact_router.get(
    "/{message_id}", response_model=AdminContactDetail, summary="One contact message"
)
async def get_contact_message(
    message_id: UUID, response: Response, _actor: ContactManager, service: Contact
) -> AdminContactDetail:
    response.headers.update(_NO_STORE)
    return await service.get(message_id)


@admin_contact_router.patch(
    "/{message_id}",
    response_model=AdminContactDetail,
    summary="Move a message along new → in_progress → closed, or edit its internal note",
)
async def update_contact_message(
    message_id: UUID,
    payload: UpdateContactRequest,
    request: Request,
    response: Response,
    actor: ContactManager,
    service: Contact,
) -> AdminContactDetail:
    response.headers.update(_NO_STORE)
    return await service.update(actor, message_id, payload, request)


# --- home page (CNT-01) -------------------------------------------------------------------


def get_home_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    products: Annotated[ProductService, Depends(get_product_service)],
    storage: Annotated[FileStorage, Depends(get_file_storage)],
) -> HomeService:
    return HomeService(session, products, CategoryRepository(session), storage)


@home_router.get(
    "",
    response_model=HomeResponse,
    summary="The whole home page: active sections in order, with fresh prices and stock",
)
async def get_home(
    response: Response, service: Annotated[HomeService, Depends(get_home_service)]
) -> HomeResponse:
    response.headers.update(_NO_STORE)
    return await service.home()


# --- admin home sections (CNT-02) ---------------------------------------------------------


def get_admin_home_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AdminHomeService:
    return AdminHomeService(session, CategoryRepository(session))


AdminHome = Annotated[AdminHomeService, Depends(get_admin_home_service)]


@admin_home_router.get(
    "",
    response_model=Page[AdminSectionResponse],
    summary="Live home sections with their items, in display order",
    dependencies=[Depends(_MANAGER), Depends(allowed_query_params("page", "limit"))],
)
async def list_sections(
    response: Response,
    paging: Annotated[PageParams, Depends(admin_page_params)],
    service: AdminHome,
) -> Page[AdminSectionResponse]:
    response.headers.update(_NO_STORE)
    return await service.list_sections(paging)


@admin_home_router.post(
    "",
    response_model=AdminSectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a home section; links and items are checked when saved",
)
async def create_section(
    payload: CreateSectionRequest,
    request: Request,
    response: Response,
    actor: Manager,
    service: AdminHome,
) -> AdminSectionResponse:
    response.headers.update(_NO_STORE)
    return await service.create(actor, payload, request)


@admin_home_router.patch(
    "/{section_id}",
    response_model=AdminSectionResponse,
    summary="Change a home section; sent items replace the list",
)
async def update_section(
    section_id: UUID,
    payload: UpdateSectionRequest,
    request: Request,
    response: Response,
    actor: Manager,
    service: AdminHome,
) -> AdminSectionResponse:
    response.headers.update(_NO_STORE)
    return await service.update(actor, section_id, payload, request)


@admin_home_router.delete(
    "/{section_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Soft delete a home section"
)
async def delete_section(
    section_id: UUID, request: Request, actor: Manager, service: AdminHome
) -> Response:
    await service.delete(actor, section_id, request)
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=_NO_STORE)


# --- banners (CNT-03) ---------------------------------------------------------------------


def get_banner_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    storage: Annotated[FileStorage, Depends(get_file_storage)],
) -> BannerService:
    return BannerService(session, CategoryRepository(session), storage)


Banners = Annotated[BannerService, Depends(get_banner_service)]


@admin_banners_router.get(
    "",
    response_model=Page[AdminBannerResponse],
    summary="Live banners, inactive and scheduled ones included, in display order",
    dependencies=[Depends(_MANAGER), Depends(allowed_query_params("page", "limit"))],
)
async def list_banners(
    response: Response,
    paging: Annotated[PageParams, Depends(admin_page_params)],
    service: Banners,
) -> Page[AdminBannerResponse]:
    response.headers.update(_NO_STORE)
    return await service.list_banners(paging)


@admin_banners_router.post(
    "",
    response_model=AdminBannerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a banner; its images and link are checked when saved",
)
async def create_banner(
    payload: CreateBannerRequest,
    request: Request,
    response: Response,
    actor: Manager,
    service: Banners,
) -> AdminBannerResponse:
    response.headers.update(_NO_STORE)
    return await service.create(actor, payload, request)


@admin_banners_router.patch(
    "/{banner_id}", response_model=AdminBannerResponse, summary="Change a banner"
)
async def update_banner(
    banner_id: UUID,
    payload: UpdateBannerRequest,
    request: Request,
    response: Response,
    actor: Manager,
    service: Banners,
) -> AdminBannerResponse:
    response.headers.update(_NO_STORE)
    return await service.update(actor, banner_id, payload, request)


@admin_banners_router.delete(
    "/{banner_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Soft delete a banner"
)
async def delete_banner(
    banner_id: UUID, request: Request, actor: Manager, service: Banners
) -> Response:
    await service.delete(actor, banner_id, request)
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=_NO_STORE)
