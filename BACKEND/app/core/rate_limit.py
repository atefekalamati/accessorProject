"""Global request rate limit, in process memory (SEC-01, ADR-060).

A sliding window per key: per client IP on ``/api/v1``, and per user on ``/api/v1/admin``.
Counters live in this process only (ADR-060, Q1): with several instances each one counts
on its own. Behind a reverse proxy every client shares the proxy's IP until OPS-04
(trusted proxy, DEFERRED) is done. The module-specific limits (OTP, discount code, payment
callback, contact form) stay where they are; this one sits in front of them.
"""

from __future__ import annotations

import ipaddress
import math
import time
from collections import OrderedDict, deque
from collections.abc import Callable
from typing import Final

from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import Settings
from app.core.errors import ErrorCode
from app.core.http_security import send_error
from app.core.metrics import MetricsRegistry

# Never limited: liveness and readiness probes.
EXEMPT_PATHS: Final = frozenset({"/api/v1/health", "/api/v1/ready"})
API_PREFIX: Final = "/api/v1"
ADMIN_PREFIX: Final = "/api/v1/admin"
# Idle keys are dropped every this many hits; at most MAX_KEYS keys are kept.
_PRUNE_EVERY: Final = 1024
MAX_KEYS: Final = 100_000


class SlidingWindowLimiter:
    """At most ``cap`` hits per key in any ``window`` seconds.

    ``hit`` records a hit and returns None, or returns the seconds until the oldest
    counted hit leaves the window (at least 1) without recording. No ``await`` happens
    inside, so one event loop needs no lock.
    """

    def __init__(self, cap: int, window: float, *, max_keys: int = MAX_KEYS) -> None:
        self.cap = cap
        self.window = window
        self.max_keys = max_keys
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()
        self._calls = 0

    def __len__(self) -> int:
        return len(self._hits)

    def hit(self, key: str, now: float) -> int | None:
        self._calls += 1
        if self._calls % _PRUNE_EVERY == 0:
            self._prune(now)
        hits = self._hits.get(key)
        if hits is None:
            if len(self._hits) >= self.max_keys:
                self._hits.popitem(last=False)  # the least recently used key
            hits = self._hits[key] = deque()
        else:
            self._hits.move_to_end(key)
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        if len(hits) >= self.cap:
            return max(1, math.ceil(hits[0] + self.window - now))
        hits.append(now)
        return None

    def _prune(self, now: float) -> None:
        idle = [
            key for key, hits in self._hits.items() if not hits or hits[-1] <= now - self.window
        ]
        for key in idle:
            del self._hits[key]


def _client_ip(scope: Scope) -> str | None:
    client = scope.get("client")
    if not client:
        return None
    try:
        address = ipaddress.ip_address(client[0])
    except ValueError:
        return None
    if address.version == 6:
        # One client usually holds a whole /64; counting single addresses would let it rotate.
        return str(ipaddress.ip_network(f"{address}/64", strict=False))
    return str(address)


def _bearer(scope: Scope) -> str | None:
    for name, value in scope.get("headers", []):
        if name == b"authorization":
            scheme, _, token = value.decode("latin-1").partition(" ")
            return token.strip() or None if scheme.lower() == "bearer" else None
    return None


class RateLimitMiddleware:
    """429 ``RATE_LIMITED`` with ``Retry-After`` once a client IP, or an admin user, is over.

    The admin limit keys on the user id of a verified access token only (signature and
    expiry, no database), so a forged token creates no key; such a request is still
    counted per IP and then refused by the route.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        settings: Settings,
        clock: Callable[[], float] = time.monotonic,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        self.app = app
        self.settings = settings
        self.metrics = metrics
        self.clock = clock
        window = settings.rate_limit_window_seconds
        self.per_ip = SlidingWindowLimiter(settings.rate_limit_per_ip, window)
        self.per_admin = SlidingWindowLimiter(settings.rate_limit_admin_per_user, window)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return
        path = str(scope.get("path", ""))
        in_api = path == API_PREFIX or path.startswith(f"{API_PREFIX}/")
        if not in_api or path.rstrip("/") in EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return
        now = self.clock()
        ip = _client_ip(scope)
        if ip is not None and (retry := self.per_ip.hit(ip, now)) is not None:
            await self._refuse(send, scope, retry, "ip")
            return
        if path.startswith(ADMIN_PREFIX) and (user := self._admin_user(scope)) is not None:
            if (retry := self.per_admin.hit(user, now)) is not None:
                await self._refuse(send, scope, retry, "user")
                return
        await self.app(scope, receive, send)

    def _admin_user(self, scope: Scope) -> str | None:
        from app.modules.auth.tokens import AccessTokenError, decode_access_token

        token = _bearer(scope)
        if token is None:
            return None
        try:
            return str(decode_access_token(token, self.settings).user_id)
        except AccessTokenError:
            return None

    async def _refuse(self, send: Send, scope: Scope, retry_after: int, scope_name: str) -> None:
        if self.metrics is not None:
            self.metrics.rate_limited(scope_name)
        await send_error(
            send,
            scope,
            ErrorCode.RATE_LIMITED,
            "Too many requests",
            headers=[(b"retry-after", str(retry_after).encode())],
            details=[{"type": f"too_many_requests_{scope_name}"}],
        )
