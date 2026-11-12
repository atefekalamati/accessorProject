"""Phase tag extraction for the CD job (OPS-09)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "phase_tag", Path(__file__).parent.parent / "scripts" / "phase_tag.py"
)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


@pytest.mark.parametrize(
    ("message", "tag"),
    [
        ("Merge pull request #5 from owner/feat/phase-2-core-domain\n\nPhase 2", "phase-2"),
        ("Phase 3: purchase flow (#9)", "phase-3"),
        ("feat: phase-12 wrap-up", "phase-12"),
        ("Merge pull request #2 from owner/feat/m1.1-repo-foundation", ""),
        ("fix: emphasize phaser docs", ""),
    ],
)
def test_phase_tag(message: str, tag: str) -> None:
    assert _MODULE.phase_tag(message) == tag
