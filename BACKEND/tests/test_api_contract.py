"""The frontend contract: browser CORS headers and the exported OpenAPI file (HANDOFF-01)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from httpx import AsyncClient

_SPEC = importlib.util.spec_from_file_location(
    "export_openapi", Path(__file__).parent.parent / "scripts" / "export_openapi.py"
)
assert _SPEC is not None and _SPEC.loader is not None
export_openapi = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(export_openapi)

ORIGIN = "http://localhost:3000"


async def test_a_preflight_allows_the_idempotency_key(client: AsyncClient) -> None:
    response = await client.options(
        "/api/v1/orders",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type,idempotency-key",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"
    allowed = response.headers["access-control-allow-headers"].lower()
    assert "idempotency-key" in allowed


async def test_retry_after_and_the_request_id_are_readable(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health", headers={"Origin": ORIGIN})

    exposed = {
        h.strip().lower() for h in response.headers["access-control-expose-headers"].split(",")
    }
    assert {"retry-after", "x-request-id"} <= exposed


def test_the_exported_openapi_file_is_current() -> None:
    expected = export_openapi.render(export_openapi.build_spec())
    current = export_openapi.OUTPUT.read_text(encoding="utf-8")

    assert current == expected, "run: python scripts/export_openapi.py"


def test_no_operation_of_the_last_released_api_was_removed() -> None:
    """A phase snapshot is what the frontend builds on (OPS-06); removing an operation
    breaks it. Rename or remove only with a new versioned path and a frontend change."""
    latest = export_openapi.latest_snapshot()
    assert latest is not None, "no snapshot in docs/api/versions"
    released = export_openapi.operations(json.loads(latest.read_text(encoding="utf-8")))
    current = export_openapi.operations(export_openapi.build_spec())

    assert sorted(released - current) == [], f"removed since {latest.name}"


def test_snapshot_names_are_phase_numbers() -> None:
    for bad in ("phase-0", "v1", "../phase-4", "phase-4.json"):
        with pytest.raises(ValueError):
            export_openapi.snapshot_path(bad)
    assert export_openapi.snapshot_path("phase-12").name == "openapi-phase-12.json"


def test_the_exported_spec_has_the_purchase_flow() -> None:
    paths = export_openapi.build_spec()["paths"]

    for path in (
        "/api/v1/auth/refresh",
        "/api/v1/cart/acknowledge-prices",
        "/api/v1/checkout/validate",
        "/api/v1/orders",
        "/api/v1/payments/init",
        "/api/v1/payments/callback",
        "/api/v1/payments/fake/{reference}/complete",
    ):
        assert path in paths
