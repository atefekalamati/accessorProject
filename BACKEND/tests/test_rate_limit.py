"""Global rate limit: per IP on /api/v1, per admin user on /api/v1/admin (SEC-01, ADR-060)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.core.rate_limit import EXEMPT_PATHS, RateLimitMiddleware, SlidingWindowLimiter
from app.main import create_app
from app.modules.auth.tokens import create_access_token

ORIGIN = "http://localhost:3000"

# --- the limiter (pure) ---------------------------------------------------------------------


def test_the_window_slides_and_retry_after_is_when_the_oldest_leaves() -> None:
    limiter = SlidingWindowLimiter(cap=2, window=60)

    assert limiter.hit("a", 0.0) is None
    assert limiter.hit("a", 10.0) is None
    assert limiter.hit("a", 15.5) == 45  # the hit at 0 leaves at 60
    assert limiter.hit("b", 15.5) is None  # keys are independent
    assert limiter.hit("a", 60.0) is None  # the hit at 0 has left
    assert limiter.hit("a", 61.0) == 9


def test_a_refused_hit_is_not_counted() -> None:
    limiter = SlidingWindowLimiter(cap=1, window=10)
    limiter.hit("a", 0.0)

    for second in range(1, 10):
        assert limiter.hit("a", float(second)) is not None
    assert limiter.hit("a", 10.0) is None


def test_retry_after_is_at_least_one_second() -> None:
    limiter = SlidingWindowLimiter(cap=1, window=1)
    limiter.hit("a", 0.0)

    assert limiter.hit("a", 0.999) == 1


def test_keys_are_bounded_and_idle_ones_are_pruned() -> None:
    limiter = SlidingWindowLimiter(cap=5, window=10, max_keys=3)
    for index in range(5):
        limiter.hit(f"k{index}", 0.0)
    assert len(limiter) == 3

    pruning = SlidingWindowLimiter(cap=5, window=10)
    for index in range(2000):
        pruning.hit(f"old{index}", 0.0)
    for index in range(1024):
        pruning.hit("fresh", 100.0 + index / 1000)
    assert len(pruning) < 100


# --- the middleware ---------------------------------------------------------------------------


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _app(settings: Settings, clock: _Clock, **caps: int) -> FastAPI:
    defaults = {"rate_limit_per_ip": 3, "rate_limit_admin_per_user": 2}
    application = create_app(settings.model_copy(update=defaults | caps))

    @application.get("/api/v1/probe")
    @application.get("/api/v1/admin/probe")
    async def probe() -> dict[str, bool]:
        return {"ok": True}

    for middleware in application.user_middleware:
        if getattr(middleware, "cls", None) is RateLimitMiddleware:
            middleware.kwargs["clock"] = clock
    return application


async def _client(application: FastAPI, ip: str = "203.0.113.5") -> AsyncClient:
    transport = ASGITransport(app=application, client=(ip, 1234))
    return AsyncClient(transport=transport, base_url="http://testserver")


async def test_an_ip_over_the_cap_gets_429_with_retry_after(settings: Settings) -> None:
    clock = _Clock()
    async with await _client(_app(settings, clock)) as client:
        allowed = [await client.get("/api/v1/probe") for _ in range(3)]
        clock.now += 20
        refused = await client.get("/api/v1/probe", headers={"Origin": ORIGIN})

    assert all(response.status_code != 429 for response in allowed)
    assert refused.status_code == 429
    assert refused.headers["retry-after"] == "40"
    body = refused.json()
    assert body["error"]["code"] == "RATE_LIMITED"
    assert body["error"]["details"] == [{"type": "too_many_requests_ip"}]
    assert body["request_id"] == refused.headers["x-request-id"]
    assert refused.headers["access-control-allow-origin"] == ORIGIN
    assert refused.headers["x-content-type-options"] == "nosniff"


async def test_the_window_frees_the_ip_again(settings: Settings) -> None:
    clock = _Clock()
    async with await _client(_app(settings, clock)) as client:
        for _ in range(3):
            await client.get("/api/v1/probe")
        clock.now += 60
        response = await client.get("/api/v1/probe")

    assert response.status_code != 429


async def test_ips_are_counted_apart(settings: Settings) -> None:
    clock = _Clock()
    application = _app(settings, clock)
    async with await _client(application, "203.0.113.5") as first:
        for _ in range(3):
            await first.get("/api/v1/probe")
        assert (await first.get("/api/v1/probe")).status_code == 429
    async with await _client(application, "203.0.113.6") as second:
        assert (await second.get("/api/v1/probe")).status_code != 429


@pytest.mark.parametrize("path", ["/api/v1/health", "/health", "/docs"])
async def test_probes_and_non_api_paths_are_never_limited(settings: Settings, path: str) -> None:
    clock = _Clock()
    async with await _client(_app(settings, clock, rate_limit_per_ip=1)) as client:
        responses = [await client.get(path) for _ in range(5)]

    assert all(response.status_code != 429 for response in responses)


async def test_a_trailing_slash_and_lookalike_paths_are_not_limited(settings: Settings) -> None:
    clock = _Clock()
    async with await _client(_app(settings, clock, rate_limit_per_ip=1)) as client:
        responses = [await client.get(path) for path in ("/api/v1/health/", "/api/v1foo") * 3]

    assert all(response.status_code != 429 for response in responses)


async def test_ipv6_clients_are_counted_per_64(settings: Settings) -> None:
    clock = _Clock()
    application = _app(settings, clock, rate_limit_per_ip=2)
    for suffix in ("1", "2"):
        async with await _client(application, f"2001:db8:1:2::{suffix}") as client:
            await client.get("/api/v1/probe")
    async with await _client(application, "2001:db8:1:2::3") as same_64:
        assert (await same_64.get("/api/v1/probe")).status_code == 429
    async with await _client(application, "2001:db8:1:3::1") as other_64:
        assert (await other_64.get("/api/v1/probe")).status_code != 429


async def test_a_lowercase_scheme_is_accepted_and_an_expired_token_is_per_ip_only(
    settings: Settings,
) -> None:
    clock = _Clock()
    application = _app(settings, clock, rate_limit_per_ip=100)
    token = create_access_token(uuid4(), uuid4(), settings, datetime.now(UTC))
    expired = create_access_token(uuid4(), uuid4(), settings, datetime.now(UTC) - timedelta(days=1))
    async with await _client(application) as client:
        for _ in range(2):
            await client.get("/api/v1/admin/probe", headers={"Authorization": f"bearer {token}"})
        refused = await client.get(
            "/api/v1/admin/probe", headers={"Authorization": f"bearer {token}"}
        )
        stale = [
            await client.get("/api/v1/admin/probe", headers={"Authorization": f"Bearer {expired}"})
            for _ in range(3)
        ]

    assert refused.status_code == 429
    assert all(response.status_code != 429 for response in stale)


def test_readiness_is_exempt_too() -> None:
    assert {"/api/v1/health", "/api/v1/ready"} <= EXEMPT_PATHS


async def test_preflights_are_not_counted(settings: Settings) -> None:
    clock = _Clock()
    async with await _client(_app(settings, clock, rate_limit_per_ip=1)) as client:
        for _ in range(5):
            preflight = await client.options(
                "/api/v1/probe",
                headers={"Origin": ORIGIN, "Access-Control-Request-Method": "GET"},
            )
            assert preflight.status_code == 200
        assert (await client.get("/api/v1/probe")).status_code != 429


async def test_an_admin_user_has_a_cap_of_their_own(settings: Settings) -> None:
    clock = _Clock()
    application = _app(settings, clock, rate_limit_per_ip=100)
    token = create_access_token(uuid4(), uuid4(), settings, datetime.now(UTC))
    other = create_access_token(uuid4(), uuid4(), settings, datetime.now(UTC))
    async with await _client(application) as client:
        for _ in range(2):
            await client.get("/api/v1/admin/probe", headers={"Authorization": f"Bearer {token}"})
        refused = await client.get(
            "/api/v1/admin/probe", headers={"Authorization": f"Bearer {token}"}
        )
        someone_else = await client.get(
            "/api/v1/admin/probe", headers={"Authorization": f"Bearer {other}"}
        )
        public = await client.get("/api/v1/probe", headers={"Authorization": f"Bearer {token}"})

    assert refused.status_code == 429
    assert refused.json()["error"]["details"] == [{"type": "too_many_requests_user"}]
    assert someone_else.status_code != 429
    assert public.status_code != 429


async def test_a_forged_admin_token_is_only_counted_per_ip(settings: Settings) -> None:
    clock = _Clock()
    application = _app(settings, clock, rate_limit_per_ip=100)
    rate_limiter: RateLimitMiddleware | None = None
    async with await _client(application) as client:
        for _ in range(5):
            response = await client.get(
                "/api/v1/admin/probe", headers={"Authorization": "Bearer forged.token.value"}
            )
            assert response.status_code == 200  # the probe needs no login
        stack = application.middleware_stack
        while stack is not None and rate_limiter is None:
            if isinstance(stack, RateLimitMiddleware):
                rate_limiter = stack
            stack = getattr(stack, "app", None)

    assert rate_limiter is not None
    assert len(rate_limiter.per_admin) == 0
    assert len(rate_limiter.per_ip) == 1


def test_the_defaults_match_the_requirements() -> None:
    fields = Settings.model_fields
    assert fields["rate_limit_per_ip"].default == 300
    assert fields["rate_limit_admin_per_user"].default == 600
    assert fields["rate_limit_window_seconds"].default == 60
