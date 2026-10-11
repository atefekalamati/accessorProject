from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PricingSetting
from app.modules.pricing.calculator import PricingPolicy
from app.shared.money import RoundingMode


def to_policy(setting: PricingSetting) -> PricingPolicy:
    """The calculator's view of the row; the mode must be a real ``RoundingMode``."""
    return PricingPolicy(
        tax_enabled=setting.tax_enabled,
        tax_rate_bps=setting.default_tax_rate_bps,
        rounding_mode=RoundingMode(setting.rounding_mode),
        rounding_step=setting.rounding_step,
        version=setting.version,
    )


class PricingSettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self) -> PricingSetting | None:
        statement = select(PricingSetting).execution_options(populate_existing=True)
        return (await self._session.scalars(statement)).one_or_none()

    async def lock(self) -> PricingSetting | None:
        """The singleton row under ``FOR UPDATE``: settings writes are serialized."""
        statement = (
            select(PricingSetting).with_for_update().execution_options(populate_existing=True)
        )
        return (await self._session.scalars(statement)).one_or_none()

    async def policy(self) -> PricingPolicy | None:
        """For CART-03 and ORD-03: the current policy, or ``None`` if the row is missing."""
        setting = await self.get()
        return None if setting is None else to_policy(setting)
