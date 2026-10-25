"""Admin discount code API shapes (DSC-04, ADR-044).

Body-shape rules are 400; rules that need the stored row (PATCH) are 422 in the service.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Final
from uuid import UUID

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)

from app.db.models import DiscountType
from app.db.models.discounts import MAX_PERCENT_BPS
from app.modules.discounts.codes import normalize_code
from app.shared.money import MAX_PRICE_TOMAN

# Server-owned fields a client may echo back from a response: dropped, never applied.
SYSTEM_FIELDS: Final = frozenset(
    {
        "id",
        "pending_count",
        "confirmed_count",
        "released_count",
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
        "deleted_at",
    }
)
EDITABLE_FIELDS: Final = (
    "value",
    "max_amount",
    "min_order_amount",
    "starts_at",
    "ends_at",
    "usage_limit_total",
    "usage_limit_per_user",
    "is_active",
)
# Fields that may be cleared with null (no cap, no minimum, open window, unlimited).
NULLABLE_FIELDS: Final = frozenset(
    {
        "max_amount",
        "min_order_amount",
        "starts_at",
        "ends_at",
        "usage_limit_total",
        "usage_limit_per_user",
    }
)

Amount = Annotated[int, Field(strict=True, ge=1, le=MAX_PRICE_TOMAN)]
# Stored and echoed in UTC, whatever offset the client sent.
Moment = Annotated[AwareDatetime, AfterValidator(lambda moment: moment.astimezone(UTC))]
Limit = Annotated[int, Field(strict=True, ge=1, le=2_000_000_000)]


def _drop_system_fields(data: Any) -> Any:
    if isinstance(data, dict):
        return {key: value for key, value in data.items() if key not in SYSTEM_FIELDS}
    return data


def check_combination(
    *,
    type: DiscountType,
    value: int,
    max_amount: int | None,
    starts_at: datetime | None,
    ends_at: datetime | None,
    usage_limit_total: int | None,
    usage_limit_per_user: int | None,
) -> str | None:
    """The first broken cross-field rule, or None (same rules as the DB CHECKs)."""
    if type is DiscountType.PERCENT and not 1 <= value <= MAX_PERCENT_BPS:
        return f"a percentage is 1 to {MAX_PERCENT_BPS} basis points"
    if type is DiscountType.FIXED and max_amount is not None:
        return "max_amount only applies to a percentage"
    if starts_at is not None and ends_at is not None and starts_at >= ends_at:
        return "starts_at must be before ends_at"
    if (
        usage_limit_total is not None
        and usage_limit_per_user is not None
        and usage_limit_per_user > usage_limit_total
    ):
        return "usage_limit_per_user cannot exceed usage_limit_total"
    return None


class CreateDiscountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    type: DiscountType
    # Basis points for a percentage (1000 = 10%), Toman for a fixed amount.
    value: Amount
    max_amount: Amount | None = None
    min_order_amount: Amount | None = None
    starts_at: Moment | None = None
    ends_at: Moment | None = None
    usage_limit_total: Limit | None = None
    usage_limit_per_user: Limit | None = None
    is_active: StrictBool = True

    @model_validator(mode="before")
    @classmethod
    def _system_fields(cls, data: Any) -> Any:
        return _drop_system_fields(data)

    @field_validator("code")
    @classmethod
    def _normalize(cls, raw: str) -> str:
        return normalize_code(raw)

    @model_validator(mode="after")
    def _combination(self) -> CreateDiscountRequest:
        problem = check_combination(
            type=self.type,
            value=self.value,
            max_amount=self.max_amount,
            starts_at=self.starts_at,
            ends_at=self.ends_at,
            usage_limit_total=self.usage_limit_total,
            usage_limit_per_user=self.usage_limit_per_user,
        )
        if problem is not None:
            raise ValueError(problem)
        return self


class UpdateDiscountRequest(BaseModel):
    """Sent fields change; ``code`` and ``type`` are accepted only unchanged (service)."""

    model_config = ConfigDict(extra="forbid")

    code: str | None = None
    type: DiscountType | None = None
    value: Amount | None = None
    max_amount: Amount | None = None
    min_order_amount: Amount | None = None
    starts_at: Moment | None = None
    ends_at: Moment | None = None
    usage_limit_total: Limit | None = None
    usage_limit_per_user: Limit | None = None
    is_active: StrictBool | None = None

    @model_validator(mode="before")
    @classmethod
    def _system_fields(cls, data: Any) -> Any:
        return _drop_system_fields(data)

    @field_validator("code")
    @classmethod
    def _normalize(cls, raw: str | None) -> str | None:
        return None if raw is None else normalize_code(raw)

    @model_validator(mode="after")
    def _fields(self) -> UpdateDiscountRequest:
        sent = self.model_fields_set
        if not sent:
            raise ValueError("at least one field is required")
        nulls = sorted(name for name in sent - NULLABLE_FIELDS if getattr(self, name) is None)
        if nulls:
            raise ValueError(f"must not be null: {', '.join(nulls)}")
        return self


class DiscountResponse(BaseModel):
    id: UUID
    code: str
    type: DiscountType
    value: int
    max_amount: int | None
    min_order_amount: int | None
    starts_at: datetime | None
    ends_at: datetime | None
    usage_limit_total: int | None
    usage_limit_per_user: int | None
    is_active: bool
    # Live and past uses (D31): pending orders, paid orders, released (cancel/refund).
    pending_count: int
    confirmed_count: int
    released_count: int
    created_by: UUID | None
    updated_by: UUID | None
    created_at: datetime
    updated_at: datetime
