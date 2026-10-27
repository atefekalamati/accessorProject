"""Dashboard and sales reports for staff with ``reports:read`` (ADM-04, ADM-05)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now
from app.modules.reports.periods import REPORT_TIMEZONE, DashboardPeriod
from app.modules.reports.repository import PeriodFigures, ReportRepository
from app.modules.reports.schemas import (
    DashboardPeriodResponse,
    DashboardPeriodsResponse,
    DashboardResponse,
)


def average_amount(amount: int, count: int) -> int:
    """Floor toman per order (PRD «داشبورد»); 0 when nothing was sold."""
    return amount // count if count else 0


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
