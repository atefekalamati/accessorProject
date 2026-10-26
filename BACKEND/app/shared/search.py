"""Shared query parsing for admin lists: mobile search and the from/to time range."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Final

from fastapi import Query

from app.core.errors import BadRequestError

# An optional '+', then 3-16 digits; a leading 0 (local format) is dropped before matching.
_MOBILE_SEARCH: Final = re.compile(r"\+?\d{3,16}")


def invalid_query(field: str, message: str) -> BadRequestError:
    return BadRequestError(
        message="Request validation failed",
        details=[{"field": f"query.{field}", "message": message, "type": "value_error"}],
    )


def is_mobile_search(value: str) -> bool:
    return _MOBILE_SEARCH.fullmatch(value) is not None


def mobile_digits(value: str | None, *, field: str = "mobile") -> str | None:
    """The digits to match inside a stored E.164 mobile, or None for no filter."""
    if value is None or value == "":
        return None
    if not is_mobile_search(value):
        raise invalid_query(field, "Must be 3-16 digits, optionally starting with '+'")
    return value.lstrip("+").lstrip("0") or None


@dataclass(frozen=True, slots=True)
class TimeRange:
    """A half-open range ``[start, end)``; either side may be open."""

    start: datetime | None = None
    end: datetime | None = None


def time_range(
    start: Annotated[datetime | None, Query(alias="from")] = None,
    end: Annotated[datetime | None, Query(alias="to")] = None,
) -> TimeRange:
    """``from`` and ``to`` query parameters: timezone-aware and ``from < to``."""
    for name, value in (("from", start), ("to", end)):
        if value is not None and value.tzinfo is None:
            raise invalid_query(name, "Must include a timezone")
    if start is not None and end is not None and start >= end:
        raise invalid_query("from", "Must be before 'to'")
    return TimeRange(start=start, end=end)
