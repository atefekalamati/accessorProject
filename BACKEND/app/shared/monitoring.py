"""``GET /metrics`` for the monitoring system (OPS-01, PRD «پایش و رخدادها» ✓, ADR-060).

Protected by ``METRICS_TOKEN`` (bearer). Without a configured token, or with a wrong one,
the endpoint answers 404 like any unknown path. Not part of the public API schema.
"""

from __future__ import annotations

import hmac
import logging
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings, get_app_settings
from app.core.errors import NotFoundError
from app.core.metrics import CONTENT_TYPE, LabelSet, MetricsRegistry
from app.db.models import Payment

logger = logging.getLogger("app.metrics")
router = APIRouter(tags=["monitoring"], include_in_schema=False)


def _authorized(request: Request, settings: Settings) -> bool:
    if settings.metrics_token is None:
        return False
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    expected = settings.metrics_token.get_secret_value()
    return scheme.lower() == "bearer" and hmac.compare_digest(token.strip(), expected)


async def _database_gauges(
    engine: AsyncEngine | None,
) -> dict[str, tuple[str, list[tuple[LabelSet, float]]]]:
    ready = 0.0
    refund_rows: list[tuple[LabelSet, float]] = []
    if engine is not None:
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
                ready = 1.0
                open_refunds = await connection.scalar(
                    select(func.count())
                    .select_from(Payment)
                    .where(Payment.status == "refund_required")
                )
                refund_rows = [((), float(open_refunds or 0))]
        except Exception:  # the scrape still answers; database_up says why
            logger.warning("metrics.database_unavailable")
    return {
        "database_up": ("1 when the database answers a query, else 0.", [((), ready)]),
        "payments_refund_required_open": (
            "Payments waiting for a manual refund (refund_required).",
            refund_rows,
        ),
    }


@router.get("/metrics")
async def metrics(
    request: Request, settings: Annotated[Settings, Depends(get_app_settings)]
) -> PlainTextResponse:
    if not _authorized(request, settings):
        raise NotFoundError(message="Not found")
    registry = cast(MetricsRegistry, request.app.state.metrics)
    engine = cast(AsyncEngine | None, getattr(request.app.state, "db_engine", None))
    body = registry.render(await _database_gauges(engine))
    return PlainTextResponse(body, media_type=CONTENT_TYPE, headers={"Cache-Control": "no-store"})
