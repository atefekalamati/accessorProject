import re
from typing import Annotated, Any, Final
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from app.core.errors import BadRequestError, NotFoundError
from app.db.models.catalog import SLUG_PATTERN
from app.modules.catalog.dependencies import get_category_service, get_product_service
from app.modules.catalog.product_query import PRODUCT_SORTS, ProductSort
from app.modules.catalog.product_service import ListingRequest, ProductService
from app.modules.catalog.schemas import (
    CategoryDetailResponse,
    CategoryFiltersResponse,
    CategoryTreeResponse,
    ProductAvailabilityResponse,
    ProductDetailResponse,
    ProductListResponse,
    ProductPricingResponse,
)
from app.modules.catalog.service import CategoryService
from app.shared.money import MAX_PRICE_TOMAN
from app.shared.pagination import (
    PageParams,
    allowed_query_params,
    public_page_params,
    resolve_sort,
)

router = APIRouter(prefix="/categories", tags=["categories"])
products_router = APIRouter(prefix="/products", tags=["products"])

_SLUG: Final = re.compile(SLUG_PATTERN)

# --- listing query (CAT-07, ADR-032) -------------------------------------------------

# Bounded so a filter cannot turn into a heavy query (PRD).
MAX_FILTER_VALUES: Final = 20
MAX_FILTER_KEY_LENGTH: Final = 50
MAX_FILTER_VALUE_LENGTH: Final = 200
# Shortcut parameter → filter key; any other key goes through ``attributes=key:value``.
_FILTER_SHORTCUTS: Final = {
    "colors": "color",
    "sizes": "size",
    "materials": "material",
    "brands": "brand",
}
_LISTING_PARAMS: Final = (
    "page",
    "limit",
    "sort",
    "min_price",
    "max_price",
    "in_stock",
    "has_discount",
    "attributes",
    *_FILTER_SHORTCUTS,
)

_Price = Annotated[int | None, Query(ge=0, le=MAX_PRICE_TOMAN)]
_Values = Annotated[list[str] | None, Query()]


def _invalid(field: str, message: str) -> dict[str, Any]:
    return {"field": f"query.{field}", "message": message, "type": "value_error"}


def _clean(raw: list[str], field: str, errors: list[dict[str, Any]]) -> list[str]:
    if len(raw) > MAX_FILTER_VALUES:
        errors.append(_invalid(field, f"At most {MAX_FILTER_VALUES} values"))
        return []
    values = [value.strip() for value in raw]
    if any(not 1 <= len(value) <= MAX_FILTER_VALUE_LENGTH for value in values):
        errors.append(_invalid(field, f"Values must be 1-{MAX_FILTER_VALUE_LENGTH} characters"))
        return []
    return values


def listing_request(
    paging: Annotated[PageParams, Depends(public_page_params)],
    sort: str | None = None,
    min_price: _Price = None,
    max_price: _Price = None,
    in_stock: bool = False,
    has_discount: bool = False,
    colors: _Values = None,
    sizes: _Values = None,
    materials: _Values = None,
    brands: _Values = None,
    attributes: _Values = None,
) -> ListingRequest:
    """Parse the shared listing query; every violation is one 400 (ADR-011)."""
    resolved: ProductSort = resolve_sort(sort, PRODUCT_SORTS, default=ProductSort.NEWEST)
    errors: list[dict[str, Any]] = []
    if min_price is not None and max_price is not None and min_price > max_price:
        errors.append(_invalid("min_price", "Must not be greater than max_price"))

    values: dict[str, set[str]] = {}
    sources: dict[str, str] = {}
    shortcuts = {"colors": colors, "sizes": sizes, "materials": materials, "brands": brands}
    for name, raw in shortcuts.items():
        for value in _clean(raw or [], name, errors):
            key = _FILTER_SHORTCUTS[name]
            values.setdefault(key, set()).add(value)
            sources.setdefault(key, f"query.{name}")
    for entry in _clean(attributes or [], "attributes", errors):
        key, separator, value = entry.partition(":")
        key, value = key.strip(), value.strip()
        if not separator or not key or not value or len(key) > MAX_FILTER_KEY_LENGTH:
            errors.append(_invalid("attributes", "Expected key:value"))
            continue
        values.setdefault(key, set()).add(value)
        sources.setdefault(key, "query.attributes")
    if errors:
        raise BadRequestError(message="Request validation failed", details=errors)
    return ListingRequest(
        params=paging,
        sort=resolved,
        min_price=min_price,
        max_price=max_price,
        in_stock=in_stock,
        has_discount=has_discount,
        values={key: frozenset(items) for key, items in values.items()},
        sources=sources,
    )


@router.get(
    "",
    response_model=CategoryTreeResponse,
    summary="Tree of visible categories, ordered by display_order",
    dependencies=[Depends(allowed_query_params())],
)
async def list_categories(
    service: Annotated[CategoryService, Depends(get_category_service)],
) -> CategoryTreeResponse:
    return await service.tree()


@router.get(
    "/{slug}",
    response_model=CategoryDetailResponse,
    summary="A visible category with its breadcrumb and visible sub-categories",
    dependencies=[Depends(allowed_query_params())],
)
async def get_category(
    slug: str,
    service: Annotated[CategoryService, Depends(get_category_service)],
) -> CategoryDetailResponse:
    _check_slug(slug)
    return await service.detail(slug)


@router.get(
    "/{slug}/filters",
    response_model=CategoryFiltersResponse,
    summary="Active filters of a visible category with the values its products have",
    dependencies=[Depends(allowed_query_params())],
)
async def get_category_filters(
    slug: str,
    service: Annotated[CategoryService, Depends(get_category_service)],
) -> CategoryFiltersResponse:
    _check_slug(slug)
    return await service.filters(slug)


@router.get(
    "/{slug}/products",
    response_model=ProductListResponse,
    summary="Published products of a visible category, filtered, sorted and paged",
    dependencies=[Depends(allowed_query_params(*_LISTING_PARAMS))],
)
async def list_category_products(
    slug: str,
    query: Annotated[ListingRequest, Depends(listing_request)],
    response: Response,
    service: Annotated[ProductService, Depends(get_product_service)],
) -> ProductListResponse:
    _check_slug(slug)
    response.headers["Cache-Control"] = "no-store"
    return await service.list_products(query, category_slug=slug)


def _check_slug(slug: str) -> None:
    # A malformed slug cannot match any category, so it is answered like an unknown one.
    if _SLUG.fullmatch(slug) is None:
        raise NotFoundError(message="Category not found")


@products_router.get(
    "",
    response_model=ProductListResponse,
    summary="Published products, optionally of one category, filtered, sorted and paged",
    dependencies=[Depends(allowed_query_params(*_LISTING_PARAMS, "category_slug"))],
)
async def list_products(
    query: Annotated[ListingRequest, Depends(listing_request)],
    response: Response,
    service: Annotated[ProductService, Depends(get_product_service)],
    category_slug: Annotated[str | None, Query(pattern=SLUG_PATTERN)] = None,
) -> ProductListResponse:
    # Price and stock are computed per request (PRD): never cache the answer.
    response.headers["Cache-Control"] = "no-store"
    return await service.list_products(query, category_slug=category_slug)


@products_router.get(
    "/{product_id}/pricing",
    response_model=ProductPricingResponse,
    summary="Current server-computed prices of a published product's variants",
    dependencies=[Depends(allowed_query_params("variant_id"))],
)
async def get_product_pricing(
    product_id: UUID,
    response: Response,
    service: Annotated[ProductService, Depends(get_product_service)],
    variant_id: UUID | None = None,
) -> ProductPricingResponse:
    response.headers["Cache-Control"] = "no-store"
    return await service.pricing(product_id, variant_id=variant_id)


@products_router.get(
    "/{product_id}/availability",
    response_model=ProductAvailabilityResponse,
    summary="Stock status of a published product's variants (no stock numbers)",
    dependencies=[Depends(allowed_query_params("variant_id"))],
)
async def get_product_availability(
    product_id: UUID,
    response: Response,
    service: Annotated[ProductService, Depends(get_product_service)],
    variant_id: UUID | None = None,
) -> ProductAvailabilityResponse:
    response.headers["Cache-Control"] = "no-store"
    return await service.availability(product_id, variant_id=variant_id)


@products_router.get(
    "/{slug}",
    response_model=ProductDetailResponse,
    summary="A published product with its active variants, prices, stock status and images",
    dependencies=[Depends(allowed_query_params())],
)
async def get_product(
    slug: str,
    response: Response,
    service: Annotated[ProductService, Depends(get_product_service)],
) -> ProductDetailResponse:
    # Validated before any query; unlike categories, the PRD wants a 400 here.
    if _SLUG.fullmatch(slug) is None:
        raise BadRequestError(
            message="Request validation failed",
            details=[{"field": "path.slug", "message": "Invalid slug", "type": "value_error"}],
        )
    # Price and stock are computed per request (PRD): never cache the answer.
    response.headers["Cache-Control"] = "no-store"
    return await service.detail(slug)
