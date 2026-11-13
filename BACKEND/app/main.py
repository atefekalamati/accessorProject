from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

from app.api.v1.router import api_router
from app.core.config import (
    Environment,
    MediaStorage,
    PaymentGatewayName,
    Settings,
    get_settings,
)
from app.core.error_reporting import build_error_reporter
from app.core.errors import ErrorResponse, register_exception_handlers
from app.core.http_security import BodySizeLimitMiddleware, SecurityHeadersMiddleware
from app.core.logging import configure_logging
from app.core.metrics import MetricsMiddleware, MetricsRegistry
from app.core.middleware import RequestContextMiddleware
from app.core.rate_limit import RateLimitMiddleware
from app.db.session import create_database_engine, create_session_factory
from app.modules.inventory.jobs import run_sweeper
from app.modules.payments.gateways import build_payment_gateway
from app.modules.payments.jobs import reconcile_pending_payments, run_reconciler
from app.modules.payments.router import fake_gateway_router
from app.shared.database.router import dev_router, readiness_router
from app.shared.health.router import router as health_router
from app.shared.media import MAX_REQUEST_BYTES
from app.shared.monitoring import router as monitoring_router
from app.shared.storage import create_file_storage


class _MediaFiles(StaticFiles):
    """Development-only file server for local media; browsers must not sniff types."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    metrics = MetricsRegistry()
    configure_logging(app_settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_database_engine(app_settings)
        app.state.db_engine = engine
        app.state.session_factory = create_session_factory(engine)
        if app_settings.payment_reconcile_seconds > 0:
            # Built at startup so production without a real gateway fails closed here.
            try:
                gateway = build_payment_gateway(app_settings, engine)
            except Exception:
                await engine.dispose()
                raise
            app.state.payment_gateway = gateway
        sweeper: asyncio.Task[None] | None = None
        if app_settings.reservation_sweep_seconds > 0:
            sweeper = asyncio.create_task(
                run_sweeper(
                    engine,
                    app_settings.reservation_sweep_seconds,
                    on_success=lambda: metrics.job_succeeded("reservation_sweep"),
                ),
                name="reservation-sweeper",
            )
        app.state.reservation_sweeper = sweeper
        reconciler: asyncio.Task[None] | None = None
        if app_settings.payment_reconcile_seconds > 0:
            reconciler = asyncio.create_task(
                run_reconciler(
                    lambda purge: reconcile_pending_payments(
                        engine, gateway, app_settings, purge=purge
                    ),
                    app_settings.payment_reconcile_seconds,
                    on_success=lambda: metrics.job_succeeded("payment_reconcile"),
                ),
                name="payment-reconciler",
            )
        app.state.payment_reconciler = reconciler
        try:
            yield
        finally:
            for task in (sweeper, reconciler):
                if task is not None:
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
            await engine.dispose()

    production = app_settings.environment is Environment.PRODUCTION
    application = FastAPI(
        title=app_settings.app_name,
        version=app_settings.app_version,
        # Off in production (ADR-060); docs/api/openapi.json is the frontend's contract.
        docs_url=None if production else "/docs",
        redoc_url=None if production else "/redoc",
        openapi_url=None if production else "/openapi.json",
        responses={
            400: {"model": ErrorResponse, "description": "Validation error"},
            401: {"model": ErrorResponse, "description": "Authentication required"},
            403: {"model": ErrorResponse, "description": "Permission denied"},
            404: {"model": ErrorResponse, "description": "Resource not found"},
            409: {"model": ErrorResponse, "description": "Conflicting state"},
            413: {"model": ErrorResponse, "description": "Request body too large"},
            422: {"model": ErrorResponse, "description": "Business rule violation"},
            429: {
                "model": ErrorResponse,
                "description": "Too many requests (see Retry-After header)",
            },
            500: {"model": ErrorResponse, "description": "Internal server error"},
            503: {"model": ErrorResponse, "description": "Service unavailable"},
        },
        lifespan=lifespan,
    )
    application.state.settings = app_settings
    application.state.metrics = metrics
    application.state.error_reporter = build_error_reporter(app_settings)
    application.state.file_storage = create_file_storage(app_settings)

    # Added innermost first: SecurityHeaders → CORS → RequestContext → metrics →
    # rate limit → body limit → routes, so a 413 or 429 still has the request id, CORS
    # and security headers and is counted (SEC-01, SEC-02, OPS-01).
    application.add_middleware(
        BodySizeLimitMiddleware,
        max_bytes=app_settings.max_request_body_bytes,
        # Twice the upload cap: the upload endpoints keep their own order (auth first, then
        # 400 over their cap, CAT-05); only far larger bodies stop here.
        multipart_max_bytes=2 * MAX_REQUEST_BYTES,
    )
    application.add_middleware(RateLimitMiddleware, settings=app_settings, metrics=metrics)
    application.add_middleware(MetricsMiddleware, registry=metrics)
    application.add_middleware(RequestContextMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins_list,
        allow_credentials="*" not in app_settings.cors_origins_list,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        # Idempotency-Key: POST /orders and /payments/init (ADR-046); without it a browser
        # preflight refuses both. Retry-After: every 429, readable by the frontend.
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "Idempotency-Key"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )
    application.add_middleware(SecurityHeadersMiddleware, hsts=production)
    register_exception_handlers(application)

    application.include_router(health_router)
    application.include_router(readiness_router)
    application.include_router(monitoring_router)
    application.include_router(api_router, prefix="/api/v1")
    if app_settings.environment is not Environment.PRODUCTION:
        application.include_router(dev_router, prefix="/api/v1")
        if app_settings.payment_gateway is PaymentGatewayName.FAKE:
            application.include_router(fake_gateway_router, prefix="/api/v1")
    if (
        app_settings.environment is Environment.DEVELOPMENT
        and app_settings.media_storage is MediaStorage.LOCAL
    ):
        application.mount(
            "/media", _MediaFiles(directory=app_settings.media_root, check_dir=False), "media"
        )
    return application


app = create_app()
