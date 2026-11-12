"""Markdown text that holds no raw HTML (D40, ADR-053).

The frontend renders Markdown through a sanitizer; the backend's part is refusing HTML at
the door. Anything an HTML parser would open as a tag, comment or declaration is refused,
including inside code spans and autolinks: a plain ``a < b`` is still accepted.
"""

from __future__ import annotations

import re
from typing import Final

_HTML_START: Final = re.compile(r"<(?:/?[A-Za-z]|!|\?)")
# Newlines and tabs are text; NUL cannot be stored in PostgreSQL at all.
_CONTROL: Final = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def check_markdown(value: str) -> str:
    """Return ``value`` unchanged, or raise ``ValueError`` (a 400 in a request body)."""
    if _CONTROL.search(value) is not None:
        raise ValueError("must not contain control characters")
    if _HTML_START.search(value) is not None:
        raise ValueError("must not contain raw HTML tags")
    return value
