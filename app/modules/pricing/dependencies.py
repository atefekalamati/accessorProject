from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.catalog.product_repository import ProductRepository
from app.modules.pricing.price_service import PriceService
from app.modules.pricing.repository import PricingSettingsRepository
from app.modules.pricing.service import PricingSettingsService


def get_pricing_settings_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PricingSettingsService:
    return PricingSettingsService(session, PricingSettingsRepository(session))


def get_price_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PriceService:
    return PriceService(session, ProductRepository(session))
