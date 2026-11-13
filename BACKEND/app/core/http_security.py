"""HTTP hardening middleware: security headers and request body size (SEC-02, ADR-060).

Both are pure ASGI middleware. Order in ``create_app`` (outermost first):
``SecurityHeadersMiddleware`` → CORS → ``RequestContextMiddleware`` → (rate limit,
SEC-01) → ``BodySizeLimitMiddleware`` → routes. So a 413 still carries the request id,
the CORS headers and the security headers. An unhandled 500 is built by Starlette's
``ServerErrorMiddleware``, outside all of these, and has none of them (ADR-060).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Final
from uuid import uuid4

from starlette.requests import ClientDisconnect
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import ERROR_STATUS, ErrorCode

_API_HEADERS: Final = (
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=(), payment=()"),
)
# Swagger UI and ReDoc (development only) load their bundles from this CDN.
_DOCS_CSP: Final = (
    b"default-src 'none'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    b"style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
    b"font-src https://fonts.gstatic.com; "
    b"img-src 'self' data: https://fastapi.tiangolo.com; "
    b"connect-src 'self'; worker-src blob:; frame-ancestors 'none'"
)
_DOCS_PATHS: Final = ("/docs", "/redoc")
# TLS ends at the reverse proxy in production; the API never serves plain HTTP there.
_HSTS: Final = (b"strict-transport-security", b"max-age=31536000; includeSubDomains")


def request_id_of(scope: Scope) -> str:
    """The id ``RequestContextMiddleware`` stored for this request, or a fresh one."""
    state = scope.get("state") or {}
    value = state.get("request_id") if isinstance(state, dict) else None
    return str(value) if value else str(uuid4())


async def send_error(
    send: Send,
    scope: Scope,
    code: ErrorCode,
    message: str,
    *,
    headers: Iterable[tuple[bytes, bytes]] = (),
    details: list[object] | None = None,
) -> None:
    """The standard error body (``{"error": ..., "request_id"}``) from ASGI middleware."""
    body = json.dumps(
        {
            "error": {"code": code.value, "message": message, "details": details or []},
            "request_id": request_id_of(scope),
        }
    ).encode()
    await send(
        {
            "type": "http.response.start",
            "status": ERROR_STATUS[code],
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                *headers,
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class SecurityHeadersMiddleware:
    """Adds the security headers to every HTTP response; never replaces a header the app
    already set (compared case-insensitively)."""

    def __init__(self, app: ASGIApp, *, hsts: bool) -> None:
        self.app = app
        self.hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        docs = str(scope.get("path", "")).startswith(_DOCS_PATHS)
        extra = [
            (name, _DOCS_CSP if docs and name == b"content-security-policy" else value)
            for name, value in _API_HEADERS
        ]
        if self.hsts:
            extra.append(_HSTS)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {name.lower() for name, _value in headers}
                headers.extend((name, value) for name, value in extra if name not in present)
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)


class BodySizeLimitMiddleware:
    """Refuses request bodies over the limit with 413 ``PAYLOAD_TOO_LARGE``.

    ``Content-Length`` above the limit is refused before anything is read. A body without
    it (chunked) is counted as it arrives; once over, the app's own answer (FastAPI turns
    a failed body read into a 400) is replaced by the 413. Multipart gets a larger limit
    (twice the upload cap), so the upload endpoints still answer auth errors and their own
    400 for a file over their cap (CAT-05).
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int, multipart_max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.multipart_max_bytes = multipart_max_bytes

    def _limit(self, scope: Scope) -> int:
        for name, value in scope.get("headers", []):
            if name == b"content-type":
                if value.split(b";", 1)[0].strip().lower() == b"multipart/form-data":
                    return self.multipart_max_bytes
                break
        return self.max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self._limit(scope)
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                if not value.isdigit():
                    await send_error(
                        send, scope, ErrorCode.VALIDATION_ERROR, "Invalid Content-Length"
                    )
                    return
                if int(value) > limit:
                    await _too_large(send, scope, limit)
                    return
                break

        received = 0
        over = False
        replaced = False

        async def counting_receive() -> Message:
            nonlocal received, over
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    over = True
                    # Stops the body read; the app's resulting answer is replaced below.
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal replaced
            if over:
                if message["type"] == "http.response.start" and not replaced:
                    replaced = True
                    await _too_large(send, scope, limit)
                return
            await send(message)

        try:
            await self.app(scope, counting_receive, guarded_send)
        except ClientDisconnect:
            # A raw body read raises ClientDisconnect after the cut: answer 413, not 500.
            if not over:
                raise
        if over and not replaced:
            await _too_large(send, scope, limit)


async def _too_large(send: Send, scope: Scope, limit: int) -> None:
    await send_error(
        send,
        scope,
        ErrorCode.PAYLOAD_TOO_LARGE,
        f"Request body is larger than {limit} bytes",
    )
