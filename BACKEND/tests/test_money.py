from __future__ import annotations

from fractions import Fraction
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError
from sqlalchemy import BigInteger, Column, MetaData, Table
from sqlalchemy.schema import CreateTable

from app.db.base import NAMING_CONVENTION
from app.shared.money import (
    DEFAULT_ROUNDING_MODE,
    DEFAULT_ROUNDING_STEP,
    RoundingMode,
    Toman,
    non_negative_check,
    round_amount,
)

UP = RoundingMode.UP
DOWN = RoundingMode.DOWN
NEAREST = RoundingMode.NEAREST


@pytest.mark.parametrize(
    ("amount", "mode", "step", "expected"),
    [
        # zero and exact multiples are unchanged in every mode
        (0, UP, 1000, 0),
        (0, DOWN, 1000, 0),
        (0, NEAREST, 1000, 0),
        (5000, UP, 1000, 5000),
        (5000, DOWN, 1000, 5000),
        (5000, NEAREST, 1000, 5000),
        # step 1: integers pass through, fractions resolve
        (1234, UP, 1, 1234),
        (1234, NEAREST, 1, 1234),
        (Fraction(1, 3), UP, 1, 1),
        (Fraction(2, 3), DOWN, 1, 0),
        (Fraction(1, 2), NEAREST, 1, 1),
        (Fraction(49, 100), NEAREST, 1, 0),
        # step 1000
        (1001, UP, 1000, 2000),
        (1999, DOWN, 1000, 1000),
        (1499, NEAREST, 1000, 1000),
        (1500, NEAREST, 1000, 2000),
        (1501, NEAREST, 1000, 2000),
        # step 5000
        (12_400, UP, 5000, 15_000),
        (12_400, DOWN, 5000, 10_000),
        (12_499, NEAREST, 5000, 10_000),
        (12_500, NEAREST, 5000, 15_000),
        # exact fractional tax: 99_999 * 9% = 8999.91
        (Fraction(99_999 * 9, 100), NEAREST, 1, 9000),
        (Fraction(99_999 * 9, 100), DOWN, 1, 8999),
        # large amounts stay exact (BigInteger range)
        (10**15 + 1, UP, 1000, 10**15 + 1000),
    ],
)
def test_round_amount_table(
    amount: int | Fraction, mode: RoundingMode, step: int, expected: int
) -> None:
    result = round_amount(amount, mode, step)

    assert result == expected
    assert type(result) is int


def test_default_rounding_is_nearest_with_step_one() -> None:
    assert DEFAULT_ROUNDING_MODE is NEAREST
    assert DEFAULT_ROUNDING_STEP == 1
    assert round_amount(Fraction(5, 2)) == 3
    assert round_amount(1500) == 1500


@pytest.mark.parametrize("amount", [1500.0, 0.5, True, "1500"])
def test_round_amount_rejects_non_integer_types(amount: Any) -> None:
    with pytest.raises(TypeError):
        round_amount(amount, NEAREST, 1)


@pytest.mark.parametrize("step", [1.0, True])
def test_round_amount_rejects_non_integer_step(step: Any) -> None:
    with pytest.raises(TypeError):
        round_amount(1000, NEAREST, step)


@pytest.mark.parametrize(("amount", "step"), [(-1, 1), (Fraction(-1, 2), 1), (1000, 0), (1000, -5)])
def test_round_amount_rejects_negative_amount_and_bad_step(
    amount: int | Fraction, step: int
) -> None:
    with pytest.raises(ValueError):
        round_amount(amount, NEAREST, step)


class _PriceIn(BaseModel):
    price: Toman


def test_toman_accepts_non_negative_int() -> None:
    assert _PriceIn.model_validate({"price": 0}).price == 0
    assert _PriceIn.model_validate_json('{"price": 1500}').price == 1500


@pytest.mark.parametrize("value", [True, False, "1500", "1500.5", 1500.0, 1500.5, -1, None])
def test_toman_rejects_invalid_values(value: Any) -> None:
    with pytest.raises(ValidationError):
        _PriceIn.model_validate({"price": value})


@pytest.mark.parametrize("raw", ['{"price": 1500.0}', '{"price": "1500"}', '{"price": true}'])
def test_toman_rejects_invalid_json(raw: str) -> None:
    with pytest.raises(ValidationError):
        _PriceIn.model_validate_json(raw)


def test_non_negative_check_renders_named_constraint() -> None:
    table = Table(
        "items",
        MetaData(naming_convention=NAMING_CONVENTION),
        Column("price", BigInteger, nullable=False),
        non_negative_check("price"),
    )

    ddl = str(CreateTable(table))

    assert "CONSTRAINT ck_items_price_non_negative CHECK (price >= 0)" in ddl
