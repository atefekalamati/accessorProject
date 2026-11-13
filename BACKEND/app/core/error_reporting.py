"""Error tracking behind an interface (OPS-01, ADR-060).

Every unhandled exception (a 500) is handed to the application's ``ErrorReporter`` with its
request id. Today the only implementation writes one structured log line; a real provider
(Sentry or similar) comes with the production decision D13 (ADR-058) as another adapter.
"""

from __future__ import annotations

import logging
from typing import Protocol

from app.core.config import Settings

logger = logging.getLogger("app.errors")


class ErrorReporter(Protocol):
    def report(self, error: BaseException, *, request_id: str, method: str, route: str) -> None:
        """Record ``error``; must never raise."""
        ...


class LogOnlyErrorReporter:
    """Logs the exception type and where it happened; the traceback is logged elsewhere."""

    def report(self, error: BaseException, *, request_id: str, method: str, route: str) -> None:
        logger.error(
            "error.reported",
            extra={
                "request_id": request_id,
                "error_type": type(error).__name__,
                "method": method,
                "route": route,
            },
        )


def build_error_reporter(settings: Settings) -> ErrorReporter:
    """Every environment uses the log-only reporter until D13 picks a provider."""
    del settings
    return LogOnlyErrorReporter()
