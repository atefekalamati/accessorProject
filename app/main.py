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
from app.core.config import Environment, MediaStorage, Settings, get_settings
from app.core.errors import ErrorResponse, register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.db.session import create_database_engine, create_session_factory
from app.modules.inventory.jobs import run_sweeper
from app.shared.database.router import dev_router, readiness_router
from app.shared.health.router import router as health_router
from app.shared.storage import create_file_storage


class _MediaFiles(StaticFiles):
    """Development-only file server for local media; browsers must not sniff types."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    configure_logging(app_settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_database_engine(app_settings)
        app.state.db_engine = engine
        app.state.session_factory = create_session_factory(engine)
        sweeper: asyncio.Task[None] | None = None
        if app_settings.reservation_sweep_seconds > 0:
            sweeper = asyncio.create_task(
                run_sweeper(engine, app_settings.reservation_sweep_seconds),
                name="reservation-sweeper",
            )
        app.state.reservation_sweeper = sweeper
        try:
            yield
        finally:
            if sweeper is not None:
                sweeper.cancel()
                with suppress(asyncio.CancelledError):
                    await sweeper
            await engine.dispose()

    application = FastAPI(
        title=app_settings.app_name,
        version=app_settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        responses={
            400: {"model": ErrorResponse, "description": "Validation error"},
            401: {"model": ErrorResponse, "description": "Authentication required"},
            403: {"model": ErrorResponse, "description": "Permission denied"},
            404: {"model": ErrorResponse, "description": "Resource not found"},
            409: {"model": ErrorResponse, "description": "Conflicting state"},
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
    application.state.file_storage = create_file_storage(app_settings)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins_list,
        allow_credentials="*" not in app_settings.cors_origins_list,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    application.add_middleware(RequestContextMiddleware)
    register_exception_handlers(application)

    application.include_router(health_router)
    application.include_router(readiness_router)
    application.include_router(api_router, prefix="/api/v1")
    if app_settings.environment is not Environment.PRODUCTION:
        application.include_router(dev_router, prefix="/api/v1")
    if (
        app_settings.environment is Environment.DEVELOPMENT
        and app_settings.media_storage is MediaStorage.LOCAL
    ):
        application.mount(
            "/media", _MediaFiles(directory=app_settings.media_root, check_dir=False), "media"
        )
    return application


app = create_app()
