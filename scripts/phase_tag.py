"""Phase tag of a merge commit message, for the CD job (OPS-09, ADR-037).

Prints ``phase-N`` when the message names the phase branch (``feat/phase-N-…``) or the
phase (``Phase N``), and nothing otherwise.
"""

from __future__ import annotations

import re
import sys

_PATTERNS = (re.compile(r"\bfeat/phase-(\d+)\b"), re.compile(r"\bphase[ -](\d+)\b", re.I))


def phase_tag(message: str) -> str:
    for pattern in _PATTERNS:
        match = pattern.search(message)
        if match:
            return f"phase-{int(match.group(1))}"
    return ""


if __name__ == "__main__":
    print(phase_tag(" ".join(sys.argv[1:])))
