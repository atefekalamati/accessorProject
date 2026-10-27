"""Dashboard and sales reports for staff with ``reports:read`` (ADM-04, ADM-05)."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now
from app.modules.reports.calendar import MAX_RANGE_DAYS, GroupBy, buckets
from app.modules.reports.periods import REPORT_TIMEZONE, DashboardPeriod
from app.modules.reports.repository import DaySales, LineSales, PeriodFigures, ReportRepository
from app.modules.reports.schemas import (
    DashboardPeriodResponse,
    DashboardPeriodsResponse,
    DashboardResponse,
    LineSalesReportResponse,
    LineSalesResponse,
    LineTotalsResponse,
    SalesBucketResponse,
    SalesFigures,
    SalesReportResponse,
)
from app.shared.search import invalid_query

CALENDAR = "jalali"
_FIGURES = (
    "order_count",
    "subtotal",
    "product_discount_total",
    "discount_code_amount",
    "tax_amount",
    "shipping_amount",
    "grand_total",
)


def average_amount(amount: int, count: int) -> int:
    """Floor toman per order (PRD «داشبورد»); 0 when nothing was sold."""
    return amount // count if count else 0


def check_range(start: date, end: date) -> None:
    """Half-open ``[from, to)`` of at most 366 Tehran days; anything else is 400."""
    if start >= end:
        raise invalid_query("from", "Must be before 'to'")
    if (end - start).days > MAX_RANGE_DAYS:
        raise invalid_query("to", f"The range must not exceed {MAX_RANGE_DAYS} days")


def _sum(days: Iterable[DaySales]) -> SalesFigures:
    rows = list(days)
    return SalesFigures(**{name: sum(getattr(row, name) for row in rows) for name in _FIGURES})


def _lines(
    start: date, end: date, sales: list[LineSales], limit: int | None
) -> LineSalesReportResponse:
    shown = sales if limit is None else sales[:limit]
    return LineSalesReportResponse(
        from_date=start,
        to_date=end,
        timezone=REPORT_TIMEZONE,
        items=[
            LineSalesResponse(
                id=item.group_id, title=item.title, units_sold=item.units_sold, amount=item.amount
            )
            for item in shown
        ],
        totals=LineTotalsResponse(
            units_sold=sum(item.units_sold for item in sales),
            amount=sum(item.amount for item in sales),
        ),
    )


def _period(figures: PeriodFigures) -> DashboardPeriodResponse:
    return DashboardPeriodResponse(
        starts_at=figures.starts_at,
        sales_count=figures.sales_count,
        sales_amount=figures.sales_amount,
        average_order_amount=average_amount(figures.sales_amount, figures.sales_count),
        new_customers=figures.new_customers,
    )


class ReportService:
    def __init__(self, session: AsyncSession) -> None:
        self._repository = ReportRepository(session)

    async def dashboard(self) -> DashboardResponse:
        now = utc_now()
        figures = await self._repository.dashboard(now)
        periods = figures.periods
        return DashboardResponse(
            generated_at=now,
            timezone=REPORT_TIMEZONE,
            periods=DashboardPeriodsResponse(
                today=_period(periods[DashboardPeriod.TODAY]),
                last_7_days=_period(periods[DashboardPeriod.LAST_7_DAYS]),
                last_30_days=_period(periods[DashboardPeriod.LAST_30_DAYS]),
            ),
            pending_payment_orders=figures.pending_payment_orders,
            refund_required_payments=figures.refund_required_payments,
            orders_to_ship=figures.orders_to_ship,
            low_stock_variants=figures.low_stock_variants,
            out_of_stock_variants=figures.out_of_stock_variants,
        )

    async def sales(self, start: date, end: date, group_by: GroupBy) -> SalesReportResponse:
        check_range(start, end)
        by_day = {row.day: row for row in await self._repository.sales_by_day(start, end)}
        result: list[SalesBucketResponse] = []
        for bucket in buckets(start, end, group_by):
            figures = _sum(by_day[day] for day in bucket.days() if day in by_day)
            result.append(
                SalesBucketResponse(
                    label=bucket.label,
                    starts_on=bucket.starts_on,
                    ends_before=bucket.ends_before,
                    **figures.model_dump(),
                )
            )
        return SalesReportResponse(
            from_date=start,
            to_date=end,
            group_by=group_by.value,
            timezone=REPORT_TIMEZONE,
            calendar=CALENDAR,
            buckets=result,
            totals=_sum(by_day.values()),
        )

    async def products(self, start: date, end: date, limit: int) -> LineSalesReportResponse:
        check_range(start, end)
        return _lines(start, end, await self._repository.sales_by_product(start, end), limit)

    async def categories(self, start: date, end: date) -> LineSalesReportResponse:
        check_range(start, end)
        return _lines(start, end, await self._repository.sales_by_category(start, end), None)
