"""Smoke test of a running API: the ephemeral staging check in CI (OPS-08, ADR-037).

Three stages, so CI can promote the smoke user to super_admin in between:

    python scripts/smoke.py login --base-url URL --mobile +98912... --token-file PATH
    python scripts/smoke.py admin --base-url URL --token-file PATH
    python scripts/smoke.py purchase --base-url URL --token-file PATH

``login`` waits for the API, checks health and readiness, signs in with the mock OTP
(fake SMS), reads the catalog and checks that a customer cannot write it. ``admin`` reuses
the same access token (permissions are read from the database on every request, ADR-018)
to create a category and read it back. ``purchase`` (PAY-06) builds a sellable product
through the admin API and buys it end to end with the fake gateway: cart, address,
checkout validate, order, payment init, paying at the gateway, callback, and checks that
the order is confirmed and the stock committed. Standard library only; the token is never
printed.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zlib
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
    headers: dict[str, str] | None = None,
    raw_body: bytes | None = None,
) -> tuple[int, Any]:
    if body is not None and raw_body is not None:
        raise ValueError("pass body or raw_body, not both")
    data = raw_body if raw_body is not None else None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(f"{base_url}{API}{path}", data=data, method=method)
    request.add_header("Accept", "application/json")
    if body is not None:
        request.add_header("Content-Type", "application/json")
    if token is not None:
        request.add_header("Authorization", f"Bearer {token}")
    for name, value in (headers or {}).items():
        request.add_header(name, value)
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


def _png() -> bytes:
    """A valid 1x1 PNG (the API re-encodes every upload)."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        payload = kind + data
        return struct.pack(">I", len(data)) + payload + struct.pack(">I", zlib.crc32(payload))

    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    pixels = zlib.compress(b"\x00\xff\x00\x00")
    return (
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", pixels) + chunk(b"IEND", b"")
    )


def _main_image(base_url: str, token: str, product_id: str) -> None:
    boundary = uuid.uuid4().hex
    body = (
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="is_main"\r\n\r\ntrue\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="s.png"\r\n'
            "Content-Type: image/png\r\n\r\n"
        ).encode()
        + _png()
        + f"\r\n--{boundary}--\r\n".encode()
    )
    status, payload = _call(
        base_url,
        "POST",
        f"/admin/products/{product_id}/media",
        token=token,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        raw_body=body,
    )
    _expect("admin: main image", status, 201, payload)


def _sellable_product(base_url: str, token: str) -> str:
    """A published product with one priced, stocked variant; returns the variant id."""
    tag = uuid.uuid4().hex[:8]
    status, category = _call(
        base_url,
        "POST",
        "/admin/categories",
        body={"title": "Smoke shop", "slug": f"smoke-shop-{tag}"},
        token=token,
    )
    _expect("admin: category", status, 201, category)
    status, product = _call(
        base_url,
        "POST",
        "/admin/products",
        body={"title": "Smoke ring", "slug": f"smoke-ring-{tag}", "category_id": category["id"]},
        token=token,
    )
    _expect("admin: product", status, 201, product)
    status, variant = _call(
        base_url,
        "POST",
        f"/admin/products/{product['id']}/variants",
        body={"sku": f"SMOKE-{tag.upper()}", "is_active": True, "base_price": 150_000},
        token=token,
    )
    _expect("admin: variant", status, 201, variant)
    _main_image(base_url, token, product["id"])
    status, payload = _call(
        base_url,
        "PATCH",
        f"/admin/products/{product['id']}/status",
        body={"status": "published"},
        token=token,
    )
    _expect("admin: publish", status, 200, payload)
    status, payload = _call(
        base_url,
        "PATCH",
        f"/admin/inventory/{variant['id']}",
        body={"adjustment_type": "increase", "quantity": 5, "reason": "smoke stock"},
        token=token,
    )
    _expect("admin: stock", status, 200, payload)
    return str(variant["id"])


def purchase(base_url: str, token_file: Path) -> None:
    token = token_file.read_text(encoding="utf-8").strip()
    variant_id = _sellable_product(base_url, token)
    status, method = _call(
        base_url,
        "POST",
        "/admin/shipping-methods",
        body={"title": f"Smoke post {uuid.uuid4().hex[:6]}", "cost": 30_000},
        token=token,
    )
    _expect("admin: shipping method", status, 201, method)

    status, payload = _call(
        base_url,
        "POST",
        "/cart/items",
        body={"variant_id": variant_id, "quantity": 2},
        token=token,
    )
    _expect("cart: add", status, 201, payload)
    status, address = _call(
        base_url,
        "POST",
        "/addresses",
        body={
            "recipient_name": "Smoke Test",
            "phone": "09120000001",
            "province": "Tehran",
            "city": "Tehran",
            "postal_code": "1234567890",
            "address_line": "Smoke St 1",
        },
        token=token,
    )
    _expect("address", status, 201, address)
    checkout = {"address_id": address["id"], "shipping_method_id": method["id"]}
    status, quote = _call(base_url, "POST", "/checkout/validate", body=checkout, token=token)
    _expect("checkout validate", status, 200, quote)
    status, order = _call(
        base_url,
        "POST",
        "/orders",
        body=checkout | {"fingerprint": quote["fingerprint"]},
        token=token,
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    _expect("order (stock reserved)", status, 201, order)
    status, started = _call(
        base_url,
        "POST",
        "/payments/init",
        body={"order_id": order["id"]},
        token=token,
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    _expect("payment init", status, 201, started)
    if started["amount"] != order["grand_total"]:
        raise SmokeError("payment init: the amount is not the order total")
    reference = urllib.parse.urlsplit(started["redirect_url"]).path.rsplit("/", 1)[1]
    status, payload = _call(
        base_url,
        "POST",
        f"/payments/fake/{reference}/complete",
        body={"result": "paid"},
    )
    _expect("pay at the fake gateway", status, 200, payload)
    status, settled = _call(base_url, "POST", "/payments/callback", body={"reference": reference})
    _expect("payment callback", status, 200, settled)
    if settled != {"outcome": "success"}:
        raise SmokeError(f"payment callback: unexpected result {settled}")
    # The callback is public and returns the outcome only; the order is read with a token.
    status, placed = _call(base_url, "GET", f"/orders/{order['order_number']}", token=token)
    _expect("order after payment", status, 200, placed)
    if (placed["status"], placed["payment_status"]) != ("confirmed", "paid"):
        raise SmokeError(f"order after payment: unexpected state {placed}")
    print("ok   order confirmed and paid")
    status, history = _call(base_url, "GET", f"/admin/inventory/{variant_id}/history", token=token)
    _expect("stock history", status, 200, history)
    commits = [
        (row["quantity"], row["total_after"], row["reserved_after"])
        for row in history["items"]
        if row["movement_type"] == "commit"
    ]
    if commits != [(2, 3, 0)]:
        raise SmokeError(f"stock: expected one commit of 2 leaving 3 in stock, got {commits}")
    print("ok   stock committed (5 - 2 = 3, nothing reserved)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("stage", choices=("login", "admin", "purchase"))
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
        elif args.stage == "admin":
            admin(base_url, args.token_file)
        else:
            purchase(base_url, args.token_file)
    except (SmokeError, KeyError, OSError, ValueError, TypeError) as error:
        print(f"FAIL {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
