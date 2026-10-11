from typing import Annotated, Final

from fastapi import APIRouter, Depends, Request, Response

from app.modules.auth.dependencies import require_permission
from app.modules.auth.service import CurrentUser
from app.modules.pricing.dependencies import get_pricing_settings_service
from app.modules.pricing.schemas import PricingSettingsResponse, UpdatePricingSettingsRequest
from app.modules.pricing.service import SETTINGS_PERMISSION, PricingSettingsService
from app.shared.pagination import allowed_query_params

router = APIRouter(prefix="/admin/pricing", tags=["admin-pricing"])

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
