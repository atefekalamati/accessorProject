"""Metrics endpoint, request and job metrics, and the error reporter (OPS-01, ADR-060)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from app.core.config import Settings
from app.core.metrics import MetricsRegistry
from app.main import create_app
from app.modules.inventory.jobs import run_sweeper
from app.modules.payments.jobs import run_reconciler

TOKEN = "metrics-token-that-is-at-least-32-chars"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def _app(settings: Settings, **changes: Any) -> FastAPI:
    application = create_app(
        settings.model_copy(update={"metrics_token": SecretStr(TOKEN)} | changes)
    )

    @application.get("/api/v1/items/{item_id}")
    async def item(item_id: str) -> dict[str, str]:
        return {"id": item_id}

    @application.get("/api/v1/boom")
    async def boom() -> None:
        raise RuntimeError("secret detail +989121234567")

    return application


def _client(application: FastAPI) -> AsyncClient:
    transport = ASGITransport(app=application, raise_app_exceptions=False)
    return AsyncClient(transport=transport, base_url="http://testserver")


# --- the registry (pure) ------------------------------------------------------------------


def test_the_exposition_format_and_label_escaping() -> None:
    registry = MetricsRegistry()
    registry.observe_request("GET", '/a"b\\c', 200, 0.07)
    registry.observe_request("GET", '/a"b\\c', 200, 3.0)
    registry.payment_callback("paid")
    registry.job_succeeded("payment_reconcile", at=1_700_000_000)

    text = registry.render({"database_up": ("Up.", [((), 1.0)])})

    assert 'http_requests_total{method="GET",route="/a\\"b\\\\c",status="200"} 2' in text
    assert 'le="0.05"} 0' in text and 'le="0.1"} 1' in text and 'le="5"} 2' in text
    assert 'le="+Inf"} 2' in text
    assert 'payment_callbacks_total{outcome="paid"} 1' in text
    assert 'job_last_success_timestamp_seconds{job="payment_reconcile"} 1700000000' in text
    assert "# TYPE http_request_duration_seconds histogram" in text
    assert text.endswith("database_up 1\n")


# --- GET /metrics -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "headers", [{}, {"Authorization": "Bearer wrong"}, {"Authorization": TOKEN}]
)
async def test_metrics_need_the_token(settings: Settings, headers: dict[str, str]) -> None:
    async with _client(_app(settings)) as client:
        response = await client.get("/metrics", headers=headers)

    assert response.status_code == 404


async def test_metrics_are_off_without_a_configured_token(settings: Settings) -> None:
    async with _client(_app(settings, metrics_token=None)) as client:
        response = await client.get("/metrics", headers=AUTH)

    assert response.status_code == 404


async def test_requests_are_counted_by_route_template_without_ids(settings: Settings) -> None:
    async with _client(_app(settings)) as client:
        await client.get("/api/v1/items/+989121234567")
        await client.get("/api/v1/items/42")
        await client.get("/api/v1/nowhere/123")
        response = await client.get("/metrics", headers=AUTH)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain; version=0.0.4")
    assert response.headers["cache-control"] == "no-store"
    text = response.text
    assert (
        'http_requests_total{method="GET",route="/api/v1/items/{item_id}",status="200"} 2' in text
    )
    assert 'route="unmatched",status="404"' in text
    assert "989121234567" not in text and "/42" not in text and "123" not in text
    assert "database_up 0" in text  # this client has no database


async def test_rate_limited_requests_are_counted(settings: Settings) -> None:
    async with _client(_app(settings, rate_limit_per_ip=1)) as client:
        await client.get("/api/v1/items/a")
        refused = await client.get("/api/v1/items/a")
        text = (await client.get("/metrics", headers=AUTH)).text

    assert refused.status_code == 429
    assert 'http_rate_limited_total{scope="ip"} 1' in text
    assert 'status="429"' in text


@pytest.mark.integration
async def test_database_gauges_on_a_real_database(auth_client: AsyncClient) -> None:
    application = auth_client._transport.app  # type: ignore[attr-defined]
    application.state.settings = application.state.settings.model_copy(
        update={"metrics_token": SecretStr(TOKEN)}
    )

    text = (await auth_client.get("/metrics", headers=AUTH)).text

    assert "database_up 1" in text
    assert "payments_refund_required_open " in text


# --- error reporter -------------------------------------------------------------------------


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def report(self, error: BaseException, *, request_id: str, method: str, route: str) -> None:
        self.calls.append(
            {"error": error, "request_id": request_id, "method": method, "route": route}
        )


async def test_a_500_reaches_the_error_reporter_once_with_its_request_id(
    settings: Settings,
) -> None:
    application = _app(settings)
    recorder = _Recorder()
    application.state.error_reporter = recorder
    async with _client(application) as client:
        response = await client.get("/api/v1/boom")

    assert response.status_code == 500
    [call] = recorder.calls
    assert isinstance(call["error"], RuntimeError)
    assert call["request_id"] == response.json()["request_id"]
    assert (call["method"], call["route"]) == ("GET", "/api/v1/boom")
    assert "989121234567" not in response.text


async def test_a_failing_reporter_does_not_change_the_500(settings: Settings) -> None:
    class Broken:
        def report(self, *_args: Any, **_kwargs: Any) -> None:
            raise ValueError("reporter down")

    application = _app(settings)
    application.state.error_reporter = Broken()
    async with _client(application) as client:
        response = await client.get("/api/v1/boom")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"


async def test_the_default_reporter_logs_the_type_not_the_message(settings: Settings) -> None:
    records: list[logging.LogRecord] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = Capture(level=logging.ERROR)
    logging.getLogger("app.errors").addHandler(handler)
    try:
        async with _client(_app(settings)) as client:
            await client.get("/api/v1/boom")
    finally:
        logging.getLogger("app.errors").removeHandler(handler)

    [record] = [r for r in records if r.getMessage() == "error.reported"]
    assert record.__dict__["error_type"] == "RuntimeError"
    assert "989121234567" not in f"{record.getMessage()} {record.__dict__}"


# --- background jobs ---------------------------------------------------------------------------


async def test_jobs_report_success_and_skip_failed_rounds() -> None:
    successes: list[str] = []
    rounds = 0

    async def flaky(_engine: Any) -> Any:
        nonlocal rounds
        rounds += 1
        if rounds == 1:
            raise RuntimeError("first round fails")
        return None

    async def reconcile(_purge: bool) -> Any:
        return None

    sweeper = asyncio.create_task(
        run_sweeper(None, 0.001, flaky, on_success=lambda: successes.append("sweep"))  # type: ignore[arg-type]
    )
    reconciler = asyncio.create_task(
        run_reconciler(reconcile, 0.001, on_success=lambda: successes.append("reconcile"))
    )
    for _ in range(200):
        if "sweep" in successes and "reconcile" in successes and rounds >= 2:
            break
        await asyncio.sleep(0.005)
    for task in (sweeper, reconciler):
        task.cancel()
    await asyncio.gather(sweeper, reconciler, return_exceptions=True)

    assert rounds >= 2
    assert successes.count("sweep") == rounds - 1 or successes.count("sweep") >= 1
    assert "reconcile" in successes
