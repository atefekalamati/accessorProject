"""Security headers, request body limit and API docs in production (SEC-02, ADR-060)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from app.core.config import Environment, Settings
from app.main import create_app
from app.shared.media import MAX_REQUEST_BYTES

ORIGIN = "http://localhost:3000"
LIMIT = 2048
HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "content-security-policy": "default-src 'none'; frame-ancestors 'none'",
    "permissions-policy": "camera=(), microphone=(), geolocation=(), payment=()",
}


def _app(settings: Settings, **changes: Any) -> FastAPI:
    application = create_app(
        settings.model_copy(update={"max_request_body_bytes": LIMIT} | changes)
    )

    @application.post("/probe")
    async def probe(request: Request) -> dict[str, int]:
        return {"size": len(await request.body())}

    @application.get("/framed")
    async def framed() -> JSONResponse:
        return JSONResponse({}, headers={"X-Frame-Options": "SAMEORIGIN"})

    return application


async def _client(application: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=application), base_url="http://testserver")


def _assert_security_headers(response: Any) -> None:
    for name, value in HEADERS.items():
        assert response.headers.get(name) == value, name


async def test_every_response_has_the_security_headers(settings: Settings) -> None:
    async with await _client(_app(settings)) as client:
        ok = await client.get("/api/v1/health")
        missing = await client.get("/api/v1/no-such-route")
        preflight = await client.options(
            "/probe", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST"}
        )

    for response in (ok, missing, preflight):
        _assert_security_headers(response)
        assert "strict-transport-security" not in response.headers


async def test_hsts_only_in_production(settings: Settings) -> None:
    production = settings.model_copy(update={"environment": Environment.PRODUCTION})
    async with await _client(_app(production)) as client:
        response = await client.get("/framed")

    assert response.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"


async def test_a_header_the_app_set_is_kept_once(settings: Settings) -> None:
    async with await _client(_app(settings)) as client:
        response = await client.get("/framed")

    assert response.headers.get_list("x-frame-options") == ["SAMEORIGIN"]


async def test_docs_are_served_outside_production_with_their_own_policy(
    settings: Settings,
) -> None:
    async with await _client(_app(settings)) as client:
        docs = await client.get("/docs")
        spec = await client.get("/openapi.json")

    assert docs.status_code == 200
    assert "cdn.jsdelivr.net" in docs.headers["content-security-policy"]
    assert spec.headers["content-security-policy"] == HEADERS["content-security-policy"]


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
async def test_docs_are_off_in_production(settings: Settings, path: str) -> None:
    production = settings.model_copy(update={"environment": Environment.PRODUCTION})
    async with await _client(_app(production)) as client:
        response = await client.get(path)

    assert response.status_code == 404


async def test_a_declared_large_body_is_refused_before_it_is_read(settings: Settings) -> None:
    async with await _client(_app(settings)) as client:
        response = await client.post(
            "/probe", content=b"x" * (LIMIT + 1), headers={"Origin": ORIGIN}
        )

    assert response.status_code == 413
    body = response.json()
    assert body["error"]["code"] == "PAYLOAD_TOO_LARGE"
    assert body["request_id"] == response.headers["x-request-id"]
    assert response.headers["access-control-allow-origin"] == ORIGIN
    _assert_security_headers(response)


async def test_a_body_at_the_limit_passes(settings: Settings) -> None:
    async with await _client(_app(settings)) as client:
        response = await client.post("/probe", content=b"x" * LIMIT)

    assert (response.status_code, response.json()) == (200, {"size": LIMIT})


async def _chunks(total: int, size: int = 512) -> AsyncIterator[bytes]:
    sent = 0
    while sent < total:
        piece = min(size, total - sent)
        sent += piece
        yield b"x" * piece


async def test_a_chunked_body_is_counted_as_it_arrives(settings: Settings) -> None:
    async with await _client(_app(settings)) as client:
        small = await client.post("/probe", content=_chunks(LIMIT))
        large = await client.post("/probe", content=_chunks(LIMIT * 3))

    assert (small.status_code, small.json()) == (200, {"size": LIMIT})
    assert large.status_code == 413
    assert large.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


async def test_a_chunked_json_body_of_a_real_endpoint_gets_413_not_400(
    settings: Settings,
) -> None:
    async with await _client(_app(settings)) as client:
        response = await client.post(
            "/api/v1/auth/request-otp",
            content=_chunks(LIMIT * 3),
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 413


@pytest.mark.parametrize("content_type", ["multipart/form-data", "Multipart/Form-Data"])
async def test_multipart_has_the_upload_limit(settings: Settings, content_type: str) -> None:
    async with await _client(_app(settings)) as client:
        allowed = await client.post(
            "/probe",
            content=b"x" * (LIMIT * 4),
            headers={"Content-Type": f"{content_type}; boundary=abc"},
        )
        refused = await client.post(
            "/probe",
            content=b"x" * (2 * MAX_REQUEST_BYTES + 1),
            headers={"Content-Type": f"{content_type}; boundary=abc"},
        )

    assert allowed.status_code == 200
    assert refused.status_code == 413


@pytest.mark.parametrize("length", ["abc", "-1", "1.5"])
async def test_an_invalid_content_length_is_400(settings: Settings, length: str) -> None:
    async with await _client(_app(settings)) as client:
        response = await client.post("/probe", content=b"x", headers={"Content-Length": length})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_a_413_in_production_still_has_hsts(settings: Settings) -> None:
    production = settings.model_copy(update={"environment": Environment.PRODUCTION})
    async with await _client(_app(production)) as client:
        response = await client.post("/probe", content=b"x" * (LIMIT + 1))

    assert response.status_code == 413
    assert "strict-transport-security" in response.headers


def test_the_default_limit_is_one_mebibyte() -> None:
    assert Settings.model_fields["max_request_body_bytes"].default == 1024 * 1024
