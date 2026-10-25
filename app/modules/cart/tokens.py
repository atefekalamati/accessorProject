"""Guest cart token: an opaque random value in an HttpOnly cookie (CART-01, D30, ADR-039).

Only its SHA-256 is stored. The token is read from the cookie only, never from the body,
query or headers, so it never reaches logs or JavaScript.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import timedelta
from typing import Final

from fastapi import Response

CART_COOKIE_NAME: Final = "cart_token"
# Every cart route and /auth/verify-otp (where the guest cart is merged) live under it.
CART_COOKIE_PATH: Final = "/api/v1"
GUEST_CART_TTL: Final = timedelta(days=30)
# secrets.token_urlsafe(32): 43 URL-safe characters.
_TOKEN_PATTERN: Final = re.compile(r"^[A-Za-z0-9_-]{43}$")


def generate_cart_token() -> str:
    """256 random bits; a plain SHA-256 is enough to store it (like refresh tokens)."""
    return secrets.token_urlsafe(32)


def hash_cart_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def parse_cart_token(raw: str | None) -> str | None:
    """The cookie value when it looks like one of our tokens; anything else is ignored."""
    if raw is None or not _TOKEN_PATTERN.fullmatch(raw):
        return None
    return raw


def set_cart_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        CART_COOKIE_NAME,
        token,
        max_age=int(GUEST_CART_TTL.total_seconds()),
        path=CART_COOKIE_PATH,
        secure=True,
        httponly=True,
        samesite="lax",
    )


def clear_cart_cookie(response: Response) -> None:
    response.delete_cookie(
        CART_COOKIE_NAME, path=CART_COOKIE_PATH, secure=True, httponly=True, samesite="lax"
    )
