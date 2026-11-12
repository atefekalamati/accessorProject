"""Admin dashboard and reports (PRD «داشبورد» ✓، «گزارش‌ها» ✓): read-only, never cached."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.auth.dependencies import require_permission
from app.modules.reports.calendar import GroupBy
from app.modules.reports.schemas import (
    DashboardResponse,
    LineSalesReportResponse,
    SalesReportResponse,
)
from app.modules.reports.service import ReportService
from app.shared.idempotency import NO_STORE
from app.shared.pagination import allowed_query_params

dashboard_router = APIRouter(prefix="/admin/dashboard", tags=["admin-reports"])
reports_router = APIRouter(prefix="/admin/reports", tags=["admin-reports"])

_READ = Depends(require_permission("reports:read"))


def get_report_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ReportService:
    return ReportService(session)


@dashboard_router.get(
    "",
    response_model=DashboardResponse,
    summary="Sales for today, 7 and 30 Tehran days, plus the open work queues and stock alerts",
    dependencies=[_READ, Depends(allowed_query_params())],
)
async def get_dashboard(
    service: Annotated[ReportService, Depends(get_report_service)],
) -> JSONResponse:
    dashboard = await service.dashboard()
    return JSONResponse(content=dashboard.model_dump(mode="json"), headers=dict(NO_STORE))


# Tehran calendar dates (Gregorian ISO), half-open [from, to), at most 366 days.
From = Annotated[date, Query(alias="from")]
To = Annotated[date, Query(alias="to")]


def _json(report: SalesReportResponse | LineSalesReportResponse) -> JSONResponse:
    return JSONResponse(
        content=report.model_dump(mode="json", by_alias=True), headers=dict(NO_STORE)
    )


@reports_router.get(
    "/sales",
    response_model=SalesReportResponse,
    summary="Successful sales per Tehran day, Saturday week or Jalali month, with totals",
    dependencies=[_READ, Depends(allowed_query_params("from", "to", "group_by"))],
)
async def sales_report(
    start: From,
    end: To,
    service: Annotated[ReportService, Depends(get_report_service)],
    group_by: GroupBy = GroupBy.DAY,
) -> JSONResponse:
    return _json(await service.sales(start, end, group_by))


@reports_router.get(
    "/products",
    response_model=LineSalesReportResponse,
    summary="Units and line totals sold per product, largest amount first",
    dependencies=[_READ, Depends(allowed_query_params("from", "to", "limit"))],
)
async def products_report(
    start: From,
    end: To,
    service: Annotated[ReportService, Depends(get_report_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> JSONResponse:
    return _json(await service.products(start, end, limit))


@reports_router.get(
    "/categories",
    response_model=LineSalesReportResponse,
    summary="Units and line totals sold per product category, largest amount first",
    dependencies=[_READ, Depends(allowed_query_params("from", "to"))],
)
async def categories_report(
    start: From,
    end: To,
    service: Annotated[ReportService, Depends(get_report_service)],
) -> JSONResponse:
    return _json(await service.categories(start, end))
