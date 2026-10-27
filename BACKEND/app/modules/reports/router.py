"""Admin dashboard and reports (PRD «داشبورد» ✓، «گزارش‌ها» ✓): read-only, never cached."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.auth.dependencies import require_permission
from app.modules.reports.schemas import DashboardResponse
from app.modules.reports.service import ReportService
from app.shared.idempotency import NO_STORE
from app.shared.pagination import allowed_query_params

dashboard_router = APIRouter(prefix="/admin/dashboard", tags=["admin-reports"])

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
