from typing import Annotated, Any, Final
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy import UnaryExpression

from app.core.errors import BadRequestError
from app.db.models import Product, ProductStatus
from app.modules.auth.dependencies import require_permission
from app.modules.auth.service import CurrentUser
from app.modules.catalog.admin_product_schemas import (
    AdminProductListItem,
    AdminProductMediaResponse,
    AdminProductResponse,
    AdminVariantResponse,
    ChangeProductStatusRequest,
    CreateProductRequest,
    CreateVariantRequest,
    ProductMediaFields,
    UpdateProductMediaRequest,
    UpdateProductRequest,
    UpdateVariantRequest,
)
from app.modules.catalog.admin_product_service import MANAGE_PERMISSION, AdminProductService
from app.modules.catalog.dependencies import get_admin_product_service
from app.modules.catalog.product_repository import ProductFilters
from app.shared.pagination import (
    Page,
    PageParams,
    admin_page_params,
    allowed_query_params,
    resolve_sort,
)
from app.shared.uploads import parse_single_file_upload

router = APIRouter(prefix="/admin", tags=["admin-products"])

_MANAGER = require_permission(MANAGE_PERMISSION)
Manager = Annotated[CurrentUser, Depends(_MANAGER)]
Service = Annotated[AdminProductService, Depends(get_admin_product_service)]
_NO_STORE: Final = {"Cache-Control": "no-store"}

# Drafts have no published_at, so the admin list sorts by creation time (ADR-030).
PRODUCT_SORTS: Final[dict[str, tuple[UnaryExpression[Any], ...]]] = {
    "newest": (Product.created_at.desc(), Product.id.desc()),
    "oldest": (Product.created_at.asc(), Product.id.asc()),
    "title": (Product.title.asc(), Product.id.asc()),
}
_MEDIA_FIELDS: Final = tuple(ProductMediaFields.model_fields)


@router.get(
    "/products",
    response_model=Page[AdminProductListItem],
    summary="List non-deleted products, including drafts and archived ones",
    # Authorization first, so an unauthenticated caller learns nothing from validation.
    dependencies=[
        Depends(_MANAGER),
        Depends(allowed_query_params("page", "limit", "q", "status", "category_id", "sort")),
    ],
)
async def list_products(
    response: Response,
    paging: Annotated[PageParams, Depends(admin_page_params)],
    service: Service,
    q: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    status_filter: Annotated[ProductStatus | None, Query(alias="status")] = None,
    category_id: UUID | None = None,
    sort: str | None = None,
) -> Page[AdminProductListItem]:
    search = None if q is None else q.strip()
    if search == "":
        raise BadRequestError(
            message="Request validation failed",
            details=[{"field": "query.q", "message": "Must not be blank", "type": "value_error"}],
        )
    order_by = resolve_sort(sort, PRODUCT_SORTS, default="newest")
    filters = ProductFilters(
        q=search,
        status=None if status_filter is None else status_filter.value,
        category_id=category_id,
    )
    response.headers.update(_NO_STORE)
    return await service.list_products(filters, order_by, paging)


@router.get("/products/{product_id}", response_model=AdminProductResponse)
async def get_product(
    product_id: UUID, response: Response, _actor: Manager, service: Service
) -> AdminProductResponse:
    response.headers.update(_NO_STORE)
    return await service.get_product(product_id)


@router.post(
    "/products",
    response_model=AdminProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a product; it always starts as a draft",
)
async def create_product(
    payload: CreateProductRequest,
    request: Request,
    response: Response,
    actor: Manager,
    service: Service,
) -> AdminProductResponse:
    response.headers.update(_NO_STORE)
    return await service.create_product(actor, payload, request)


@router.patch("/products/{product_id}", response_model=AdminProductResponse)
async def update_product(
    product_id: UUID,
    payload: UpdateProductRequest,
    request: Request,
    response: Response,
    actor: Manager,
    service: Service,
) -> AdminProductResponse:
    response.headers.update(_NO_STORE)
    return await service.update_product(actor, product_id, payload, request)


@router.patch(
    "/products/{product_id}/status",
    response_model=AdminProductResponse,
    summary="Change the publish status along the allowed transitions",
)
async def change_product_status(
    product_id: UUID,
    payload: ChangeProductStatusRequest,
    request: Request,
    response: Response,
    actor: Manager,
    service: Service,
) -> AdminProductResponse:
    response.headers.update(_NO_STORE)
    return await service.change_status(actor, product_id, payload, request)


@router.delete(
    "/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft delete a product and its variants",
)
async def delete_product(
    product_id: UUID, request: Request, actor: Manager, service: Service
) -> Response:
    await service.delete_product(actor, product_id, request)
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=_NO_STORE)


@router.post(
    "/products/{product_id}/variants",
    response_model=AdminVariantResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a variant; an initial price also needs pricing:update",
)
async def create_variant(
    product_id: UUID,
    payload: CreateVariantRequest,
    request: Request,
    response: Response,
    actor: Manager,
    service: Service,
) -> AdminVariantResponse:
    response.headers.update(_NO_STORE)
    return await service.create_variant(actor, product_id, payload, request)


@router.patch(
    "/product-variants/{variant_id}",
    response_model=AdminVariantResponse,
    summary="Update a variant (prices change only through the pricing endpoints)",
)
async def update_variant(
    variant_id: UUID,
    payload: UpdateVariantRequest,
    request: Request,
    response: Response,
    actor: Manager,
    service: Service,
) -> AdminVariantResponse:
    response.headers.update(_NO_STORE)
    return await service.update_variant(actor, variant_id, payload, request)


@router.delete("/product-variants/{variant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_variant(
    variant_id: UUID, request: Request, actor: Manager, service: Service
) -> Response:
    await service.delete_variant(actor, variant_id, request)
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=_NO_STORE)


@router.post(
    "/products/{product_id}/media",
    response_model=AdminProductMediaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a product image (multipart: file, alt_text, variant_id, display_order, "
    "is_main)",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["file"],
                        "properties": {
                            "file": {"type": "string", "format": "binary"},
                            "alt_text": {"type": "string", "maxLength": 200},
                            "variant_id": {"type": "string", "format": "uuid"},
                            "display_order": {"type": "integer", "minimum": 0},
                            "is_main": {"type": "boolean"},
                        },
                    }
                }
            },
        }
    },
)
async def upload_product_media(
    product_id: UUID,
    request: Request,
    response: Response,
    actor: Manager,
    service: Service,
) -> AdminProductMediaResponse:
    # The body is read only here, after authentication and the permission check.
    upload = await parse_single_file_upload(request, allowed_fields=_MEDIA_FIELDS)
    try:
        fields = ProductMediaFields.model_validate(upload.fields)
    except ValidationError as exc:
        errors = [{**error, "loc": ("body", *error["loc"])} for error in exc.errors()]
        raise RequestValidationError(errors) from None
    response.headers.update(_NO_STORE)
    return await service.upload_media(actor, product_id, upload.data, fields, request)


@router.patch("/products/{product_id}/media/{media_id}", response_model=AdminProductMediaResponse)
async def update_product_media(
    product_id: UUID,
    media_id: UUID,
    payload: UpdateProductMediaRequest,
    request: Request,
    response: Response,
    actor: Manager,
    service: Service,
) -> AdminProductMediaResponse:
    response.headers.update(_NO_STORE)
    return await service.update_media(actor, product_id, media_id, payload, request)


@router.delete("/products/{product_id}/media/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product_media(
    product_id: UUID, media_id: UUID, request: Request, actor: Manager, service: Service
) -> Response:
    await service.delete_media(actor, product_id, media_id, request)
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=_NO_STORE)
