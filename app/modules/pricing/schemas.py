"""Pricing settings API shapes (PRC-05, ADR-033)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Final
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from app.shared.money import MAX_ROUNDING_STEP, MAX_TAX_RATE_BPS, RoundingMode

# Server-owned fields a client may send but never sets: dropped before validation, while
# any other unknown key is still a 400 (same rule as ADR-030).
SYSTEM_FIELDS: Final = frozenset(
    {"id", "singleton", "currency", "version", "updated_by", "updated_at"}
)
EDITABLE_FIELDS: Final = ("tax_enabled", "default_tax_rate_bps", "rounding_mode", "rounding_step")

TaxRateBps = Annotated[int, Field(strict=True, ge=0, le=MAX_TAX_RATE_BPS)]
RoundingStep = Annotated[int, Field(strict=True, ge=1, le=MAX_ROUNDING_STEP)]


class PricingSettingsResponse(BaseModel):
    currency: str
    # Store-wide switch. In v1 no API sets a variant's tax_enabled (ADR-030), so turning
    # this on does not change any price yet (ADR-033).
    tax_enabled: bool
    # Basis points: 1000 = 10%.
    default_tax_rate_bps: int
    rounding_mode: RoundingMode
    rounding_step: int
    # Bumped by every change; checkout fingerprints it (ADR-027).
    version: int
    updated_by: UUID | None
    updated_at: datetime


class UpdatePricingSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tax_enabled: StrictBool | None = None
    default_tax_rate_bps: TaxRateBps | None = None
    rounding_mode: RoundingMode | None = None
    rounding_step: RoundingStep | None = None

    @model_validator(mode="before")
    @classmethod
    def _drop_system_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {key: value for key, value in data.items() if key not in SYSTEM_FIELDS}
        return data

    @model_validator(mode="after")
    def _check_fields(self) -> UpdatePricingSettingsRequest:
        if not self.model_fields_set:
            raise ValueError("at least one field is required")
        nulls = sorted(name for name in self.model_fields_set if getattr(self, name) is None)
        if nulls:
            raise ValueError(f"must not be null: {', '.join(nulls)}")
        return self
