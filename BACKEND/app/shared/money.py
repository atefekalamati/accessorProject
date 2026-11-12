"""Money primitives: integer Toman amounts and the single rounding function (ADR-001, ADR-014).

Rules:
- Every amount is a non-negative ``int`` in Toman. ``float`` is never used for money.
- Discounts are stored as positive amounts and subtracted; an amount is never negative.
- Intermediate values (e.g. percentage tax) may be exact ``Fraction``s; they become ``int``
  only through ``round_amount``, which the pricing service calls exactly once per total.
- Conversion to Rial happens only inside the payment gateway adapter.

Column pattern for money fields::

    price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    __table_args__ = (non_negative_check("price"),)
"""

from __future__ import annotations

import math
from enum import StrEnum
from fractions import Fraction
from typing import Annotated

from pydantic import Field
from sqlalchemy import CheckConstraint

Toman = Annotated[int, Field(strict=True, ge=0)]
"""Pydantic type for API amounts: rejects bool, str (even ``"1500"``), float and negatives."""


class RoundingMode(StrEnum):
    UP = "up"
    DOWN = "down"
    NEAREST = "nearest"  # half-up; NEAREST with step=1 means "no rounding"


DEFAULT_ROUNDING_MODE = RoundingMode.NEAREST
DEFAULT_ROUNDING_STEP = 1
MAX_ROUNDING_STEP = 1_000_000
# Upper bound of one unit price (ADR-027): quantity × price sums stay far below BIGINT max.
MAX_PRICE_TOMAN = 1_000_000_000_000
# Tax rates are integer basis points (1000 = 10%), never floats (ADR-027).
MAX_TAX_RATE_BPS = 10_000


def round_amount(
    amount: int | Fraction,
    mode: RoundingMode = DEFAULT_ROUNDING_MODE,
    step: int = DEFAULT_ROUNDING_STEP,
) -> int:
    """Round a non-negative amount to a multiple of ``step`` Toman using ``mode``."""
    if isinstance(amount, bool) or not isinstance(amount, int | Fraction):
        raise TypeError("amount must be int or Fraction, never float")
    if isinstance(step, bool) or not isinstance(step, int):
        raise TypeError("step must be int")
    if step <= 0:
        raise ValueError("step must be positive")
    if amount < 0:
        raise ValueError("amount must not be negative")

    units = Fraction(amount) / step
    if mode is RoundingMode.UP:
        rounded = math.ceil(units)
    elif mode is RoundingMode.DOWN:
        rounded = math.floor(units)
    else:
        rounded = math.floor(units + Fraction(1, 2))
    return rounded * step


def non_negative_check(column: str) -> CheckConstraint:
    """``CHECK (<column> >= 0)`` for a ``BigInteger`` money column."""
    return CheckConstraint(f"{column} >= 0", name=f"{column}_non_negative")
