"""Tehran day boundaries for the dashboard and reports (D39, ADR-055).

Times are stored in UTC; days, weeks and months start at Tehran midnight. The conversion
runs in PostgreSQL, which ships the IANA time zone database (Python's ``zoneinfo`` has no
data on Windows without the extra ``tzdata`` package). The day offsets are pure.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Final

from sqlalchemy import ColumnElement, DateTime, Interval, cast, func, literal

REPORT_TIMEZONE: Final = "Asia/Tehran"


class DashboardPeriod(StrEnum):
    TODAY = "today"
    LAST_7_DAYS = "last_7_days"
    LAST_30_DAYS = "last_30_days"


# Whole Tehran days before today that each period also covers: today and the 6 or 29
# days before it, so "7 days" is the last seven calendar days including today.
DAYS_BEFORE_TODAY: Final[dict[DashboardPeriod, int]] = {
    DashboardPeriod.TODAY: 0,
    DashboardPeriod.LAST_7_DAYS: 6,
    DashboardPeriod.LAST_30_DAYS: 29,
}


def local_time(moment: ColumnElement[Any]) -> ColumnElement[Any]:
    """A UTC ``timestamptz`` as Tehran wall-clock time (``timestamp``)."""
    return func.timezone(REPORT_TIMEZONE, moment)


def from_local_time(wall_clock: ColumnElement[Any]) -> ColumnElement[datetime]:
    """Tehran wall-clock time (``timestamp``) back to a UTC ``timestamptz``."""
    return func.timezone(REPORT_TIMEZONE, wall_clock, type_=DateTime(timezone=True))


def day_start(now: datetime, days_before: int) -> ColumnElement[datetime]:
    """The UTC instant of Tehran midnight ``days_before`` days before ``now``'s day."""
    moment = literal(now, DateTime(timezone=True))
    midnight = func.date_trunc("day", local_time(moment))
    back = cast(literal(f"{days_before} days"), Interval)
    return from_local_time(midnight - back)
