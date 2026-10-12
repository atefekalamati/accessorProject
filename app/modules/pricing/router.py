from typing import Annotated, Final
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from app.modules.auth.dependencies import require_any_permission, require_permission
from app.modules.auth.service import CurrentUser
from app.modules.pricing.dependencies import get_price_service, get_pricing_settings_service
from app.modules.pricing.price_service import PRICING_PERMISSION, PriceService
from app.modules.pricing.schemas import (
    PriceHistoryItem,
    PricingSettingsResponse,
    UpdatePriceRequest,
    UpdatePricingSettingsRequest,
    VariantPriceResponse,
)
from app.modules.pricing.service import SETTINGS_PERMISSION, PricingSettingsService
from app.shared.pagination import Page, PageParams, admin_page_params, allowed_query_params

router = APIRouter(prefix="/admin/pricing", tags=["admin-pricing"])
prices_router = APIRouter(prefix="/admin", tags=["admin-pricing"])

# v1 has no separate read permission: reading the settings needs the write one (ADR-033).
_SETTINGS_ADMIN = require_permission(SETTINGS_PERMISSION)
Service = Annotated[PricingSettingsService, Depends(get_pricing_settings_service)]
_NO_STORE: Final = {"Cache-Control": "no-store"}


@router.get(
    "/settings",
    response_model=PricingSettingsResponse,
    summary="Store-wide tax and rounding settings",
    dependencies=[Depends(_SETTINGS_ADMIN), Depends(allowed_query_params())],
)
async def get_pricing_settings(response: Response, service: Service) -> PricingSettingsResponse:
    response.headers.update(_NO_STORE)
    return await service.get()


@router.patch(
    "/settings",
    response_model=PricingSettingsResponse,
    summary="Change tax and rounding settings (bumps the settings version)",
)
async def update_pricing_settings(
    payload: UpdatePricingSettingsRequest,
    request: Request,
    response: Response,
    actor: Annotated[CurrentUser, Depends(_SETTINGS_ADMIN)],
    service: Service,
) -> PricingSettingsResponse:
    response.headers.update(_NO_STORE)
    return await service.update(actor, payload, request)


# --- price changes (PRC-03, ADR-035) ----------------------------------------------------

_PRICE_EDITOR = require_permission(PRICING_PERMISSION)
PriceEditor = Annotated[CurrentUser, Depends(_PRICE_EDITOR)]
Prices = Annotated[PriceService, Depends(get_price_service)]


@prices_router.patch(
    "/product-variants/{variant_id}/price",
    response_model=VariantPriceResponse,
    summary="Change a variant's price (history + audit; bumps price_version)",
)
async def update_variant_price(
    variant_id: UUID,
    payload: UpdatePriceRequest,
    request: Request,
    response: Response,
    actor: PriceEditor,
    service: Prices,
) -> VariantPriceResponse:
    response.headers.update(_NO_STORE)
    return await service.update_variant_price(actor, variant_id, payload, request)


@prices_router.patch(
    "/products/{product_id}/price",
    response_model=VariantPriceResponse,
    summary="Change the price of a single-variant product (422 with several variants)",
)
async def update_product_price(
    product_id: UUID,
    payload: UpdatePriceRequest,
    request: Request,
    response: Response,
    actor: PriceEditor,
    service: Prices,
) -> VariantPriceResponse:
    response.headers.update(_NO_STORE)
    return await service.update_product_price(actor, product_id, payload, request)


@prices_router.get(
    "/products/{product_id}/price-history",
    response_model=Page[PriceHistoryItem],
    summary="Price changes of a product, newest first",
    dependencies=[
        Depends(require_any_permission(PRICING_PERMISSION, "catalog:manage")),
        Depends(allowed_query_params("page", "limit")),
    ],
)
async def get_price_history(
    product_id: UUID,
    response: Response,
    paging: Annotated[PageParams, Depends(admin_page_params)],
    service: Prices,
) -> Page[PriceHistoryItem]:
    response.headers.update(_NO_STORE)
    return await service.history(product_id, paging)
