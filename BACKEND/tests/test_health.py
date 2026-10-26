from __future__ import annotations

from uuid import UUID

import pytest
from httpx import AsyncClient


@pytest.mark.parametrize("path", ["/health", "/api/v1/health"])
async def test_health_endpoint(client: AsyncClient, path: str) -> None:
    response = await client.get(path)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["version"] == "0.1.0"
    assert payload["environment"] == "testing"
    assert UUID(payload["request_id"])
    assert response.headers["X-Request-ID"] == payload["request_id"]


async def test_valid_request_id_is_propagated(client: AsyncClient) -> None:
    request_id = "a389c6be-9e4a-4f79-852d-20f9a5509630"

    response = await client.get("/health", headers={"X-Request-ID": request_id})

    assert response.headers["X-Request-ID"] == request_id
    assert response.json()["request_id"] == request_id


async def test_http_errors_have_stable_contract(client: AsyncClient) -> None:
    response = await client.get("/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "HTTP_404", "message": "Not Found", "details": []},
        "request_id": response.headers["X-Request-ID"],
    }


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
async def test_api_documentation_is_enabled(client: AsyncClient, path: str) -> None:
    response = await client.get(path)

    assert response.status_code == 200


async def test_openapi_exposes_both_health_routes(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")

    paths = response.json()["paths"]
    assert "/health" in paths
    assert "/api/v1/health" in paths
    assert "ErrorResponse" in response.json()["components"]["schemas"]
