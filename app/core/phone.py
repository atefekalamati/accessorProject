from __future__ import annotations

import re

# Canonical storage format for Iranian mobile numbers: E.164, e.g. +989121234567.
MOBILE_E164_PATTERN = r"^\+989[0-9]{9}$"

_LOCAL_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "0123456789" * 2)
_SEPARATORS = re.compile(r"[\s\-()]")
_NATIONAL_MOBILE = re.compile(r"9[0-9]{9}")
_PREFIXES = ("+98", "0098", "0")


class InvalidPhoneError(ValueError):
    """Raised when a value is not a valid Iranian mobile number."""


def normalize_phone(value: str) -> str:
    """Return ``value`` as an E.164 Iranian mobile number (``+989XXXXXXXXX``).

    Accepts the ``09…``, ``+98…`` and ``0098…`` forms, Persian or Arabic-Indic
    digits, and spaces, hyphens or parentheses as separators.
    """
    candidate = _SEPARATORS.sub("", value.translate(_LOCAL_DIGITS))
    for prefix in _PREFIXES:
        if candidate.startswith(prefix):
            national = candidate[len(prefix) :]
            break
    else:
        raise InvalidPhoneError("Mobile number must start with 09, +98 or 0098")
    if _NATIONAL_MOBILE.fullmatch(national) is None:
        raise InvalidPhoneError("Mobile number must be 09 followed by 9 digits")
    return f"+98{national}"
