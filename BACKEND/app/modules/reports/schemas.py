"""Dashboard and report shapes (ADM-04, ADM-05; PRD «داشبورد» ✓، «گزارش‌ها» ✓).

Integer toman everywhere and no personal data.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


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


class SalesFigures(BaseModel):
    order_count: int
    subtotal: int
    product_discount_total: int
    discount_code_amount: int
    tax_amount: int
    shipping_amount: int
    grand_total: int


class SalesBucketResponse(SalesFigures):
    # Jalali: YYYY-MM-DD of the first day (day, week) or YYYY-MM (month).
    label: str
    # Tehran calendar days [starts_on, ends_before), clipped to the query range.
    starts_on: date
    ends_before: date


class SalesReportResponse(BaseModel):
    from_date: date = Field(serialization_alias="from")
    to_date: date = Field(serialization_alias="to")
    group_by: str
    timezone: str
    calendar: str
    buckets: list[SalesBucketResponse]
    totals: SalesFigures


class LineSalesResponse(BaseModel):
    id: UUID
    title: str
    units_sold: int
    amount: int


class LineTotalsResponse(BaseModel):
    units_sold: int
    amount: int


class LineSalesReportResponse(BaseModel):
    from_date: date = Field(serialization_alias="from")
    to_date: date = Field(serialization_alias="to")
    timezone: str
    items: list[LineSalesResponse]
    # Over every group in the range, also those past ``limit``.
    totals: LineTotalsResponse
