from __future__ import annotations

import re

import pytest

from app.core.phone import MOBILE_E164_PATTERN, InvalidPhoneError, normalize_phone


@pytest.mark.parametrize(
    "raw",
    [
        "09121234567",
        "+989121234567",
        "00989121234567",
        "۰۹۱۲۱۲۳۴۵۶۷",
        "٠٩١٢١٢٣٤٥٦٧",
        "+۹۸۹۱۲۱۲۳۴۵۶۷",
        "0912 123 4567",
        "0912-123-4567",
        "(0912) 1234567",
        " 09121234567 ",
    ],
)
def test_normalize_phone_accepts_supported_forms(raw: str) -> None:
    assert normalize_phone(raw) == "+989121234567"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "9121234567",
        "989121234567",
        "0912123456",
        "091212345678",
        "08121234567",
        "+9809121234567",
        "+19121234567",
        "0912123456a",
        "0912१२३४५६७",
    ],
)
def test_normalize_phone_rejects_invalid_values(raw: str) -> None:
    with pytest.raises(InvalidPhoneError):
        normalize_phone(raw)


def test_normalized_value_matches_storage_pattern() -> None:
    assert re.fullmatch(MOBILE_E164_PATTERN, normalize_phone("09351234567"))
