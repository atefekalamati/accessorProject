"""Removal of secrets and personal data before values leave the process (logs, audit)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Final

REDACTED: Final = "***"

# Matched as case-insensitive substrings, so future keys such as ``otp_code``,
# ``api_secret`` or ``set_cookie`` are covered without listing them.
SENSITIVE_KEY_PARTS: Final = (
    "token",
    "secret",
    "password",
    "otp",
    "authorization",
    "cookie",
    "api_key",
    "hash",
)

# ASCII, Persian (U+06F0-U+06F9) and Arabic-Indic (U+0660-U+0669) digits.
_DIGITS: Final = "0-9۰-۹٠-٩"
_ZERO: Final = "[0۰٠]"
_EIGHT: Final = "[8۸٨]"
_NINE: Final = "[9۹٩]"

# A bare ``code`` key is redacted only when it looks like a one-time code, so error
# codes such as ``NOT_FOUND`` stay readable.
_OTP_LIKE: Final = re.compile(rf"[{_DIGITS}]{{4,8}}")

_BEARER: Final = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\-._~+/]+=*")
_JWT: Final = re.compile(r"\beyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*")
# Prefers over-masking: only a neighbouring digit (i.e. part of a longer number) blocks a
# match, so ``mobile09121234567`` and ``order-09121234567`` are still masked.
_PHONE: Final = re.compile(
    rf"(?<![{_DIGITS}])"
    rf"(?P<prefix>\+{_NINE}{_EIGHT}|{_ZERO}{_ZERO}{_NINE}{_EIGHT}|{_ZERO})"
    rf"(?P<head>{_NINE}[{_DIGITS}]{{2}})"
    rf"[{_DIGITS}]{{3}}"
    rf"(?P<tail>[{_DIGITS}]{{4}})"
    rf"(?![{_DIGITS}])"
)


def is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def _is_otp_like(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return 4 <= len(str(abs(value))) <= 8
    return isinstance(value, str) and _OTP_LIKE.fullmatch(value) is not None


def mask_phone(text: str) -> str:
    """Mask Iranian mobile numbers, e.g. ``+989121234567`` -> ``+98912***4567``."""
    return _PHONE.sub(lambda m: f"{m['prefix']}{m['head']}{REDACTED}{m['tail']}", text)


def mask_text(text: str) -> str:
    """Mask secrets and phone numbers found by value inside free text."""
    text = _BEARER.sub(f"Bearer {REDACTED}", text)
    text = _JWT.sub(REDACTED, text)
    return mask_phone(text)


def redact(value: Any) -> Any:
    """Return a copy of ``value`` with sensitive keys and values masked.

    Mappings and sequences are walked recursively; other objects are returned as is.
    """
    if isinstance(value, str):
        return mask_text(value)
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            if is_sensitive_key(key) or (key.lower() == "code" and _is_otp_like(item)):
                result[key] = REDACTED
            else:
                result[key] = redact(item)
        return result
    if isinstance(value, list | tuple | set | frozenset):
        return [redact(item) for item in value]
    return value
