"""Access JWTs and opaque refresh tokens; no HTTP or cookie handling here (ADR-012)."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Final
from uuid import UUID, uuid4

import jwt

from app.core.config import Settings

# The only accepted algorithm; decoding never trusts the token header's "alg".
JWT_ALGORITHM: Final = "HS256"
ACCESS_TOKEN_TYPE: Final = "access"
_REQUIRED_CLAIMS: Final = ("exp", "iat", "sub", "sid", "typ", "jti")


class AccessTokenError(Exception):
    """An access token that is malformed, expired, mis-signed or of the wrong type."""


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    """Identity only; roles and permissions are always read from the database."""

    user_id: UUID
    session_id: UUID


def _jwt_key(settings: Settings) -> str:
    return settings.jwt_secret.get_secret_value()


def create_access_token(user_id: UUID, session_id: UUID, settings: Settings, now: datetime) -> str:
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "sid": str(session_id),
        "typ": ACCESS_TOKEN_TYPE,
        "jti": uuid4().hex,
        "iat": now,
        "exp": now + timedelta(seconds=settings.access_token_ttl_seconds),
    }
    return jwt.encode(payload, _jwt_key(settings), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str, settings: Settings) -> AccessTokenClaims:
    try:
        payload = jwt.decode(
            token,
            _jwt_key(settings),
            algorithms=[JWT_ALGORITHM],
            options={"require": list(_REQUIRED_CLAIMS)},
        )
        if payload["typ"] != ACCESS_TOKEN_TYPE:
            raise AccessTokenError("Not an access token")
        return AccessTokenClaims(user_id=UUID(payload["sub"]), session_id=UUID(payload["sid"]))
    except (jwt.PyJWTError, ValueError, TypeError, AttributeError) as exc:
        raise AccessTokenError("Invalid access token") from exc


def generate_refresh_token() -> str:
    """An opaque 256-bit random token; only its hash is stored."""
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    """SHA-256 as 64 hex characters.

    A plain digest is enough here (unlike OTPs): the token has 256 bits of entropy,
    so it cannot be brute-forced from its hash.
    """
    return hashlib.sha256(token.encode()).hexdigest()
