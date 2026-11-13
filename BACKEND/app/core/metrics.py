"""Process metrics in the Prometheus text format, without a client library (OPS-01, ADR-060).

One ``MetricsRegistry`` per application (``app.state.metrics``). Labels are route templates
(``/api/v1/orders/{order_id}``), methods, statuses and fixed outcome names only: never ids,
mobiles or other personal data. Values are per process, like the rate limit.
"""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Final

from starlette.types import ASGIApp, Message, Receive, Scope, Send

CONTENT_TYPE: Final = "text/plain; version=0.0.4; charset=utf-8"
DURATION_BUCKETS: Final = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
UNMATCHED_ROUTE: Final = "unmatched"

LabelSet = tuple[tuple[str, str], ...]


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _labels(labels: LabelSet) -> str:
    if not labels:
        return ""
    return "{" + ",".join(f'{name}="{_escape(value)}"' for name, value in labels) + "}"


def _number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else repr(float(value))


class MetricsRegistry:
    def __init__(self) -> None:
        self._requests: dict[LabelSet, int] = defaultdict(int)
        self._duration_buckets: dict[LabelSet, list[int]] = {}
        self._duration_sum: dict[LabelSet, float] = defaultdict(float)
        self._duration_count: dict[LabelSet, int] = defaultdict(int)
        self._rate_limited: dict[LabelSet, int] = defaultdict(int)
        self._callbacks: dict[LabelSet, int] = defaultdict(int)
        self._job_success: dict[str, float] = {}

    # --- recording -------------------------------------------------------------------------

    def observe_request(self, method: str, route: str, status: int, seconds: float) -> None:
        self._requests[(("method", method), ("route", route), ("status", str(status)))] += 1
        key: LabelSet = (("method", method), ("route", route))
        buckets = self._duration_buckets.setdefault(key, [0] * len(DURATION_BUCKETS))
        for index, bound in enumerate(DURATION_BUCKETS):
            if seconds <= bound:
                buckets[index] += 1
        self._duration_sum[key] += seconds
        self._duration_count[key] += 1

    def rate_limited(self, scope: str) -> None:
        self._rate_limited[(("scope", scope),)] += 1

    def payment_callback(self, outcome: str) -> None:
        self._callbacks[(("outcome", outcome),)] += 1

    def job_succeeded(self, job: str, at: float | None = None) -> None:
        self._job_success[job] = time.time() if at is None else at

    # --- exposition ------------------------------------------------------------------------

    def render(self, gauges: Mapping[str, tuple[str, Iterable[tuple[LabelSet, float]]]]) -> str:
        """The whole exposition; ``gauges`` are values read at scrape time (name → help, rows)."""
        lines: list[str] = []

        def family(name: str, kind: str, help_text: str, rows: Iterable[tuple[str, float]]) -> None:
            lines.append(f"# HELP {name} {help_text}")
            lines.append(f"# TYPE {name} {kind}")
            lines.extend(f"{series} {_number(value)}" for series, value in rows)

        def counter_rows(name: str, data: Mapping[LabelSet, int]) -> list[tuple[str, float]]:
            return [(f"{name}{_labels(labels)}", value) for labels, value in sorted(data.items())]

        family(
            "http_requests_total",
            "counter",
            "HTTP responses by method, route template and status.",
            counter_rows("http_requests_total", self._requests),
        )
        duration: list[tuple[str, float]] = []
        for labels in sorted(self._duration_count):
            for bound, count in zip(DURATION_BUCKETS, self._duration_buckets[labels], strict=True):
                le = (*labels, ("le", _number(bound)))
                duration.append((f"http_request_duration_seconds_bucket{_labels(le)}", count))
            inf = (*labels, ("le", "+Inf"))
            duration.append(
                (
                    f"http_request_duration_seconds_bucket{_labels(inf)}",
                    self._duration_count[labels],
                )
            )
            duration.append(
                (f"http_request_duration_seconds_sum{_labels(labels)}", self._duration_sum[labels])
            )
            duration.append(
                (
                    f"http_request_duration_seconds_count{_labels(labels)}",
                    self._duration_count[labels],
                )
            )
        family(
            "http_request_duration_seconds",
            "histogram",
            "Time to the end of the response, by method and route template.",
            duration,
        )
        family(
            "http_rate_limited_total",
            "counter",
            "Requests refused by the global rate limit, by scope (ip or user).",
            counter_rows("http_rate_limited_total", self._rate_limited),
        )
        family(
            "payment_callbacks_total",
            "counter",
            "Processed payment callbacks by outcome.",
            counter_rows("payment_callbacks_total", self._callbacks),
        )
        family(
            "job_last_success_timestamp_seconds",
            "gauge",
            "Unix time of the last successful round of each background job.",
            [
                (f"job_last_success_timestamp_seconds{_labels((('job', job),))}", at)
                for job, at in sorted(self._job_success.items())
            ],
        )
        for name, (help_text, rows) in gauges.items():
            family(
                name,
                "gauge",
                help_text,
                [(f"{name}{_labels(labels)}", value) for labels, value in rows],
            )
        return "\n".join(lines) + "\n"


class MetricsMiddleware:
    """Counts every HTTP response (429 and 413 included) by its route template."""

    def __init__(self, app: ASGIApp, *, registry: MetricsRegistry) -> None:
        self.app = app
        self.registry = registry

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        status = 500

        async def recording_send(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, recording_send)
        finally:
            route = getattr(scope.get("route"), "path", None) or UNMATCHED_ROUTE
            self.registry.observe_request(
                str(scope.get("method", "")), route, status, time.perf_counter() - started
            )
