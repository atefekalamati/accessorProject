from __future__ import annotations

import hashlib
import hmac

from app.core.config import Settings


def otp_hash_key(settings: Settings) -> bytes:
    """Return the OTP HMAC key; fail closed when OTP_HASH_SECRET is not configured."""
    if settings.otp_hash_secret is None:
        raise RuntimeError("OTP_HASH_SECRET is not configured")
    return settings.otp_hash_secret.get_secret_value().encode()


def hash_otp_code(code: str, mobile: str, key: bytes) -> str:
    """HMAC-SHA256 of an OTP bound to its mobile, as 64 hex characters.

    A keyed hash is required because the 6-digit code space is trivially brute-forced
    from a plain digest; binding the mobile makes a hash useless for any other number.
    """
    message = f"{mobile}:{code}".encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def verify_otp_code(code: str, mobile: str, key: bytes, code_hash: str) -> bool:
    """Constant-time comparison of a submitted code against a stored hash."""
    return hmac.compare_digest(hash_otp_code(code, mobile, key), code_hash)
