"""Pure discount code rules (DSC-02, ADR-039, ADR-043).

Decides whether a code applies and why not; the amount itself is computed only by the
pricing calculator (``price_order``, ADR-031). No database access: callers load the code
and the live redemption counts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.core.errors import BusinessRuleError, ErrorCode
from app.db.models import DiscountCode, DiscountType
from app.modules.pricing.calculator import CodeDiscount


class Rejection(StrEnum):
    # Unknown, deleted, inactive or not started yet: one answer, so neither an inactive nor
    # an upcoming code leaks. Expired, exhausted and below-minimum do reveal that the code
    # exists; accepted for UX, the failed-attempt rate limit is the defence (ADR-043).
    INVALID = "invalid"
    EXPIRED = "expired"
    EXHAUSTED = "exhausted"
    USER_EXHAUSTED = "user_exhausted"
    BELOW_MINIMUM = "below_minimum"
    # The calculator found nothing the code applies to (code_applied is False).
    NO_ELIGIBLE_LINES = "no_eligible_lines"


@dataclass(frozen=True, slots=True)
class CodeRules:
    type: DiscountType
    value: int
    max_amount: int | None
    min_order_amount: int | None
    starts_at: datetime | None
    ends_at: datetime | None
    usage_limit_total: int | None
    usage_limit_per_user: int | None
    is_active: bool
    deleted: bool


@dataclass(frozen=True, slots=True)
class Usage:
    # Live (pending or confirmed) redemptions of the code.
    total_live: int
    # Live redemptions under the shopper's verified mobile; None while there is none (a
    # guest): the per-user limit is then checked at POST /orders instead.
    user_live: int | None


def rules_of(code: DiscountCode) -> CodeRules:
    return CodeRules(
        type=DiscountType(code.type),
        value=code.value,
        max_amount=code.max_amount,
        min_order_amount=code.min_order_amount,
        starts_at=code.starts_at,
        ends_at=code.ends_at,
        usage_limit_total=code.usage_limit_total,
        usage_limit_per_user=code.usage_limit_per_user,
        is_active=code.is_active,
        deleted=code.deleted_at is not None,
    )


def check_code(
    rules: CodeRules | None, *, at: datetime, subtotal: int, usage: Usage
) -> Rejection | None:
    """Why the code cannot apply now, or None. The first failing rule wins, in this order:
    invalid (incl. not started), expired, exhausted, per-user exhausted, below the minimum.

    ``subtotal`` is the minimum-order basis: the priced lines after product discounts,
    before the code, tax and shipping (``OrderPricing.subtotal - product_discount_total``
    of a pass without the code). The window is half-open: valid in [starts_at, ends_at).
    """
    if at.tzinfo is None:
        raise ValueError("at must be timezone-aware")
    if rules is None or rules.deleted or not rules.is_active:
        return Rejection.INVALID
    if rules.starts_at is not None and at < rules.starts_at:
        return Rejection.INVALID
    if rules.ends_at is not None and at >= rules.ends_at:
        return Rejection.EXPIRED
    if rules.usage_limit_total is not None and usage.total_live >= rules.usage_limit_total:
        return Rejection.EXHAUSTED
    if (
        rules.usage_limit_per_user is not None
        and usage.user_live is not None
        and usage.user_live >= rules.usage_limit_per_user
    ):
        return Rejection.USER_EXHAUSTED
    if rules.min_order_amount is not None and subtotal < rules.min_order_amount:
        return Rejection.BELOW_MINIMUM
    return None


def to_code_discount(rules: CodeRules) -> CodeDiscount:
    """The calculator's view; a code covers the whole cart in v1 (D33)."""
    if rules.type is DiscountType.PERCENT:
        return CodeDiscount(percent_bps=rules.value, max_amount=rules.max_amount)
    return CodeDiscount(fixed_amount=rules.value)


def discount_error(rejection: Rejection) -> BusinessRuleError:
    """422 DISCOUNT_NOT_APPLICABLE; never states limits, counts or amounts."""
    return BusinessRuleError(
        code=ErrorCode.DISCOUNT_NOT_APPLICABLE,
        message="This discount code cannot be applied",
        details=[{"field": "code", "type": rejection.value}],
    )
