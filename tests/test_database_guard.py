from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import (
    TEST_DATABASE_GUARD_EXIT_CODE,
    pytest_sessionstart,
    unsafe_test_database_reason,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("value", [None, ""])
def test_unset_url_is_allowed(value: str | None) -> None:
    assert unsafe_test_database_reason(value) is None


@pytest.mark.parametrize(
    "value",
    [
        "postgresql+asyncpg://postgres:test@localhost:55432/project_ak_test",
        "postgresql+asyncpg://u:p@db/x_test",
    ],
)
def test_database_name_ending_with_test_is_allowed(value: str) -> None:
    assert unsafe_test_database_reason(value) is None


@pytest.mark.parametrize(
    "value",
    [
        "postgresql+asyncpg://u:p@localhost:5432/project_ak",
        "postgresql+asyncpg://u:p@localhost:5432/test_project_ak",
        "postgresql+asyncpg://u:p@localhost:5432/project_ak_testing",
        "postgresql+asyncpg://u:p@localhost:5432/project_ak_TEST",
        "postgresql+asyncpg://u:p@localhost:5432",
        "not a url",
    ],
)
def test_unsafe_database_url_is_rejected(value: str) -> None:
    assert unsafe_test_database_reason(value) is not None


def test_sessionstart_exits_on_unsafe_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql+asyncpg://u:p@localhost/project_ak")
    with pytest.raises(pytest.exit.Exception) as excinfo:
        pytest_sessionstart(pytest.Session.__new__(pytest.Session))
    assert excinfo.value.returncode == TEST_DATABASE_GUARD_EXIT_CODE


def test_whole_session_aborts_before_running_tests() -> None:
    env = {**os.environ, "TEST_DATABASE_URL": "postgresql+asyncpg://u:p@localhost/project_ak"}
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_health.py"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == TEST_DATABASE_GUARD_EXIT_CODE
    assert "must point to a database whose name ends with '_test'" in result.stdout + result.stderr
    assert "passed" not in result.stdout
