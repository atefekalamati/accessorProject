"""Pricing API shapes: settings (PRC-05, ADR-033) and price changes (PRC-03, ADR-035)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Final
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StringConstraints,
    model_validator,
)

from app.db.models.pricing import MAX_PRICE_REASON_LENGTH
from app.shared.money import MAX_PRICE_TOMAN, MAX_ROUNDING_STEP, MAX_TAX_RATE_BPS, RoundingMode

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


# --- price changes (PRC-03, ADR-035) ----------------------------------------------------

PRICE_FIELDS: Final = ("base_price", "sale_price", "sale_start_at", "sale_end_at")
# Server-owned fields of a variant a client may echo back; dropped, never applied.
VARIANT_SYSTEM_FIELDS: Final = frozenset(
    {
        "id",
        "product_id",
        "price_version",
        "tax_enabled",
        "updated_by",
        "updated_at",
        "created_at",
        "deleted_at",
    }
)

Price = Annotated[int, Field(strict=True, ge=1, le=MAX_PRICE_TOMAN)]
Reason = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_PRICE_REASON_LENGTH),
]


class UpdatePriceRequest(BaseModel):
    """Fields sent are changed; fields left out keep their value.

    Checks that need only the body are 400 here; checks against the stored price are 422
    in the service (ADR-011, ADR-035).
    """

    model_config = ConfigDict(extra="forbid")

    base_price: Price | None = None
    sale_price: Price | None = None
    sale_start_at: AwareDatetime | None = None
    sale_end_at: AwareDatetime | None = None
    reason: Reason | None = None

    @model_validator(mode="before")
    @classmethod
    def _drop_system_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {key: value for key, value in data.items() if key not in VARIANT_SYSTEM_FIELDS}
        return data

    @model_validator(mode="after")
    def _check_body(self) -> UpdatePriceRequest:
        sent = self.model_fields_set
        if not sent & set(PRICE_FIELDS):
            raise ValueError("at least one price field is required")
        if "base_price" in sent and self.base_price is None:
            raise ValueError("base_price must not be null")
        if "sale_price" in sent and self.sale_price is None:
            if self.sale_start_at is not None or self.sale_end_at is not None:
                raise ValueError("removing sale_price also removes the sale window")
        if (
            self.base_price is not None
            and self.sale_price is not None
            and self.sale_price > self.base_price
        ):
            raise ValueError("sale_price must not exceed base_price")
        if (
            self.sale_start_at is not None
            and self.sale_end_at is not None
            and self.sale_start_at >= self.sale_end_at
        ):
            raise ValueError("sale_start_at must be before sale_end_at")
        return self


class VariantPriceResponse(BaseModel):
    variant_id: UUID
    product_id: UUID
    base_price: int | None
    sale_price: int | None
    sale_start_at: datetime | None
    sale_end_at: datetime | None
    price_version: int


class PriceHistoryItem(BaseModel):
    id: UUID
    variant_id: UUID
    old_base_price: int | None
    new_base_price: int
    old_sale_price: int | None
    new_sale_price: int | None
    old_sale_start_at: datetime | None
    new_sale_start_at: datetime | None
    old_sale_end_at: datetime | None
    new_sale_end_at: datetime | None
    reason: str | None
    changed_by: UUID | None
    created_at: datetime
