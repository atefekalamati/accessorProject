"""Report buckets on the Iranian calendar (ADM-05, ADR-055): pure, no database.

Days are Tehran calendar days (the SQL groups by them). A week starts on Saturday; a month
is a Solar Hijri (Jalali) month. The query range is at most 366 days, so walking it day by
day is cheap.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from typing import Final

MAX_RANGE_DAYS: Final = 366
_SATURDAY: Final = 5  # date.weekday()
# Days before each Gregorian month in a common year.
_DAYS_BEFORE_MONTH: Final = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)


class GroupBy(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


def to_jalali(day: date) -> tuple[int, int, int]:
    """The Solar Hijri ``(year, month, day)`` of a Gregorian date (33-year arithmetic rule,
    exact for the years this shop will see)."""
    year = day.year + 1 if day.month > 2 else day.year
    days = (
        355666
        + 365 * day.year
        + (year + 3) // 4
        - (year + 99) // 100
        + (year + 399) // 400
        + day.day
        + _DAYS_BEFORE_MONTH[day.month - 1]
    )
    jalali_year = -1595 + 33 * (days // 12053)
    days %= 12053
    jalali_year += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jalali_year += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        return jalali_year, 1 + days // 31, 1 + days % 31
    return jalali_year, 7 + (days - 186) // 30, 1 + (days - 186) % 30


def _jalali_label(day: date) -> str:
    year, month, day_of_month = to_jalali(day)
    return f"{year:04d}-{month:02d}-{day_of_month:02d}"


def _key(day: date, group_by: GroupBy) -> tuple[int, ...]:
    if group_by is GroupBy.DAY:
        return (day.toordinal(),)
    if group_by is GroupBy.WEEK:
        return ((day - timedelta(days=(day.weekday() - _SATURDAY) % 7)).toordinal(),)
    year, month, _ = to_jalali(day)
    return (year, month)


@dataclass(frozen=True, slots=True)
class Bucket:
    """``[starts_on, ends_before)`` clipped to the query range; ``label`` is Jalali:
    ``YYYY-MM-DD`` of the first day (day, week) or ``YYYY-MM`` (month)."""

    label: str
    starts_on: date
    ends_before: date

    def days(self) -> Iterator[date]:
        for offset in range((self.ends_before - self.starts_on).days):
            yield self.starts_on + timedelta(days=offset)


def buckets(start: date, end: date, group_by: GroupBy) -> list[Bucket]:
    """Every bucket of ``[start, end)`` in order, empty ones included."""
    if not start < end:
        raise ValueError("start must be before end")
    result: list[Bucket] = []
    first = start
    day = start
    while day <= end:
        if day == end or _key(day, group_by) != _key(first, group_by):
            label = _jalali_label(first)
            if group_by is GroupBy.MONTH:
                label = label[:7]
            result.append(Bucket(label=label, starts_on=first, ends_before=day))
            first = day
        if day == end:  # never step past ``end`` (date.max would overflow)
            break
        day += timedelta(days=1)
    return result
