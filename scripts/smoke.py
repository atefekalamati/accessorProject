"""Smoke test of a running API: the ephemeral staging check in CI (OPS-08, ADR-037).

Two stages, so CI can promote the smoke user to super_admin in between:

    python scripts/smoke.py login --base-url URL --mobile +98912... --token-file PATH
    python scripts/smoke.py admin --base-url URL --token-file PATH

``login`` waits for the API, checks health and readiness, signs in with the mock OTP
(fake SMS), reads the catalog and checks that a customer cannot write it. ``admin`` reuses
the same access token (permissions are read from the database on every request, ADR-018)
to create a category and read it back. Standard library only; the token is never printed.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

API = "/api/v1"
TIMEOUT_SECONDS = 10


class SmokeError(Exception):
    pass


def _call(
    base_url: str,
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    token: str | None = None,
) -> tuple[int, Any]:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(f"{base_url}{API}{path}", data=data, method=method)
    request.add_header("Accept", "application/json")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    if token is not None:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, raw = error.code, error.read()
    return status, json.loads(raw) if raw else None


def _expect(name: str, actual: int, expected: int, payload: Any = None) -> None:
    if actual != expected:
        detail = payload.get("error") if isinstance(payload, dict) else payload
        raise SmokeError(f"{name}: expected HTTP {expected}, got {actual}: {detail}")
    print(f"ok   {name} ({actual})")


def _wait_for_health(base_url: str, wait_seconds: float) -> None:
    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            status, payload = _call(base_url, "GET", "/health")
            if status == 200:
                _expect("health", status, 200)
                return
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            status, payload = 0, "unreachable"
        if time.monotonic() > deadline:
            _expect("health", status, 200, payload)
        time.sleep(1)


def login(base_url: str, mobile: str, code: str, token_file: Path, wait: float) -> None:
    _wait_for_health(base_url, wait)
    status, payload = _call(base_url, "GET", "/ready")
    _expect("ready (database)", status, 200, payload)

    status, payload = _call(base_url, "POST", "/auth/request-otp", body={"mobile": mobile})
    _expect("request OTP (fake SMS)", status, 200, payload)
    status, payload = _call(
        base_url, "POST", "/auth/verify-otp", body={"mobile": mobile, "code": code}
    )
    _expect("verify OTP", status, 200, payload)
    token = payload["access_token"]

    status, payload = _call(base_url, "GET", "/categories")
    _expect("catalog read", status, 200, payload)
    status, payload = _call(
        base_url,
        "POST",
        "/admin/categories",
        body={"title": "Smoke", "slug": "smoke-denied"},
        token=token,
    )
    _expect("customer cannot write the catalog", status, 403, payload)
    token_file.write_text(token, encoding="utf-8")


def admin(base_url: str, token_file: Path) -> None:
    token = token_file.read_text(encoding="utf-8").strip()
    slug = f"smoke-{uuid.uuid4().hex[:8]}"
    status, payload = _call(
        base_url,
        "POST",
        "/admin/categories",
        body={"title": "Smoke category", "slug": slug},
        token=token,
    )
    _expect("admin write (create category)", status, 201, payload)
    status, payload = _call(base_url, "GET", f"/categories/{slug}")
    _expect("admin write is readable", status, 200, payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("stage", choices=("login", "admin"))
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--mobile", default="+989120000001")
    parser.add_argument("--code", default="123456", help="the mock OTP code")
    parser.add_argument("--wait", type=float, default=60, help="seconds to wait for health")
    args = parser.parse_args(argv)
    base_url = args.base_url.rstrip("/")
    try:
        if args.stage == "login":
            login(base_url, args.mobile, args.code, args.token_file, args.wait)
        else:
            admin(base_url, args.token_file)
    except (SmokeError, KeyError, OSError, ValueError) as error:
        print(f"FAIL {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
