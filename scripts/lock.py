"""Regenerate requirements.lock and requirements-dev.lock from pyproject.toml (SEC-06).

Usage: python scripts/lock.py [--upgrade]

Existing pins are kept while they still satisfy pyproject.toml, so a plain run only changes
the locks when pyproject.toml changed. CI runs it and fails on any diff (drift check).
--upgrade re-resolves every package to the newest allowed version.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

LOCKS: dict[str, list[str]] = {
    "requirements.lock": [],
    "requirements-dev.lock": ["--extra", "dev"],
}


def main() -> int:
    upgrade = ["--upgrade"] if "--upgrade" in sys.argv[1:] else []
    for output, extra in LOCKS.items():
        command = [
            sys.executable,
            "-m",
            "uv",
            "pip",
            "compile",
            "pyproject.toml",
            *extra,
            # One lock for every platform: Linux in CI/Docker and Windows locally.
            "--universal",
            "--python-version",
            "3.12",
            "--generate-hashes",
            "--quiet",
            "--custom-compile-command",
            "python scripts/lock.py",
            "--output-file",
            output,
            *upgrade,
        ]
        result = subprocess.run(command, cwd=ROOT, check=False)
        if result.returncode != 0:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
