"""Dashboard and report shapes (ADM-04, ADM-05; PRD «داشبورد» ✓، «گزارش‌ها» ✓).

Integer toman everywhere and no personal data.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DashboardPeriodResponse(BaseModel):
    # Tehran midnight (as UTC) where the period starts; it ends at ``generated_at``.
    starts_at: datetime
    sales_count: int
    sales_amount: int
    # Floor of sales_amount / sales_count; 0 without sales.
    average_order_amount: int
    new_customers: int


class DashboardPeriodsResponse(BaseModel):
    today: DashboardPeriodResponse
    last_7_days: DashboardPeriodResponse
    last_30_days: DashboardPeriodResponse


class DashboardResponse(BaseModel):
    generated_at: datetime
    timezone: str
    periods: DashboardPeriodsResponse
    # Right now, not per period.
    pending_payment_orders: int
    refund_required_payments: int
    orders_to_ship: int
    low_stock_variants: int
    out_of_stock_variants: int
