import re
from typing import Annotated, Final

from fastapi import APIRouter, Depends

from app.core.errors import NotFoundError
from app.db.models.catalog import SLUG_PATTERN
from app.modules.catalog.dependencies import get_category_service
from app.modules.catalog.schemas import (
    CategoryDetailResponse,
    CategoryFiltersResponse,
    CategoryTreeResponse,
)
from app.modules.catalog.service import CategoryService
from app.shared.pagination import allowed_query_params

router = APIRouter(prefix="/categories", tags=["categories"])

_SLUG: Final = re.compile(SLUG_PATTERN)


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


def _check_slug(slug: str) -> None:
    # A malformed slug cannot match any category, so it is answered like an unknown one.
    if _SLUG.fullmatch(slug) is None:
        raise NotFoundError(message="Category not found")
