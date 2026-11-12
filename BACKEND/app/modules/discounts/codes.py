"""Discount code text rules (DSC-01, ADR-042)."""

from __future__ import annotations

import re
from typing import Final

from app.db.models.discounts import MAX_CODE_LENGTH

# ASCII only, checked before upper-casing: str.upper() maps some non-ASCII letters to ASCII
# ('ı' → 'I', 'ß' → 'SS'), which would let different inputs collapse into one code.
_CODE: Final = re.compile(rf"[A-Za-z0-9_-]{{3,{MAX_CODE_LENGTH}}}", re.ASCII)


def normalize_code(raw: str) -> str:
    """The stored form of a code: trimmed and upper case; ValueError if malformed."""
    cleaned = raw.strip()
    if not _CODE.fullmatch(cleaned):
        raise ValueError(f"A code is 3 to {MAX_CODE_LENGTH} ASCII letters, digits, '-' or '_'")
    return cleaned.upper()
