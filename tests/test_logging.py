from __future__ import annotations

import json
import logging
from typing import Any

import pytest

import app.core.logging as app_logging
from app.core.logging import REDACTION_FAILED_MESSAGE, JsonFormatter
from app.core.redaction import REDACTED

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.c2lnbmF0dXJlLXZhbHVl"
logger = logging.getLogger("tests.logging")


def _emit(
    caplog: pytest.LogCaptureFixture,
    message: str,
    *args: object,
    extra: dict[str, Any] | None = None,
) -> str:
    with caplog.at_level(logging.INFO, logger=logger.name):
        logger.info(message, *args, extra=extra)
    return JsonFormatter().format(caplog.records[-1])


@pytest.mark.parametrize(
    "key",
    [
        "token",
        "refresh_token",
        "Access_Token",
        "client_secret",
        "api_secret",
        "password",
        "password_hash",
        "otp",
        "otp_code",
        "Authorization",
        "cookie",
        "set_cookie",
        "api_key",
    ],
)
def test_sensitive_keys_are_redacted_by_substring(
    caplog: pytest.LogCaptureFixture, key: str
) -> None:
    output = _emit(caplog, "event", extra={key: "s3cr3t-value"})

    assert "s3cr3t-value" not in output
    assert json.loads(output)[key] == REDACTED


def test_nested_sensitive_keys_are_redacted(caplog: pytest.LogCaptureFixture) -> None:
    output = _emit(
        caplog,
        "event",
        extra={"payload": {"user": {"otp_hash": "hash-abc"}, "items": [{"token": "tok-xyz"}]}},
    )

    assert "hash-abc" not in output
    assert "tok-xyz" not in output
    assert json.loads(output)["payload"]["items"][0]["token"] == REDACTED


@pytest.mark.parametrize("value", ["1234", "12345678", 123456, "۱۲۳۴۵۶", "٤٥٦٧"])
def test_code_key_is_redacted_when_otp_like(
    caplog: pytest.LogCaptureFixture, value: str | int
) -> None:
    output = _emit(caplog, "event", extra={"code": value})

    assert json.loads(output)["code"] == REDACTED


@pytest.mark.parametrize("value", ["NOT_FOUND", "123", "123456789", True, None])
def test_code_key_is_kept_when_not_otp_like(
    caplog: pytest.LogCaptureFixture, value: object
) -> None:
    output = _emit(caplog, "event", extra={"code": value})

    assert json.loads(output)["code"] == value


def test_non_sensitive_values_are_unchanged(caplog: pytest.LogCaptureFixture) -> None:
    extra = {
        "request_id": "3f2b8c1e-5d7a-4123-8456-2b9e4f6a1c3d",
        "path": "/api/v1/products",
        "status_code": 404,
        "duration_ms": 1.5,
    }
    output = _emit(caplog, "request.completed", extra=extra)

    parsed = json.loads(output)
    assert parsed["message"] == "request.completed"
    for key, value in extra.items():
        assert parsed[key] == value


@pytest.mark.parametrize(
    ("raw", "masked"),
    [
        ("+989121234567", "+98912***4567"),
        ("09121234567", "0912***4567"),
        ("00989121234567", "0098912***4567"),
        ("۰۹۱۲۱۲۳۴۵۶۷", "۰۹۱۲***۴۵۶۷"),
        ("+٩٨٩١٢١٢٣٤٥٦٧", "+٩٨٩١٢***٤٥٦٧"),
    ],
)
def test_phone_is_masked_in_message_and_extras(
    caplog: pytest.LogCaptureFixture, raw: str, masked: str
) -> None:
    output = _emit(caplog, "otp sent to %s", raw, extra={"mobile": raw})

    parsed = json.loads(output)
    assert raw not in output
    assert parsed["message"] == f"otp sent to {masked}"
    assert parsed["mobile"] == masked


@pytest.mark.parametrize(
    ("raw", "masked"),
    [
        ("mobile09121234567", "mobile0912***4567"),
        ("order-09121234567", "order-0912***4567"),
        ("user_09121234567_x", "user_0912***4567_x"),
        ("tel:+989121234567.", "tel:+98912***4567."),
        ("09121234567abc", "0912***4567abc"),
    ],
)
def test_phone_adjacent_to_non_digits_is_masked(
    caplog: pytest.LogCaptureFixture, raw: str, masked: str
) -> None:
    output = _emit(caplog, "event %s", raw, extra={"ref": raw})

    parsed = json.loads(output)
    assert "09121234567" not in output
    assert "9121234567" not in output
    assert parsed["message"] == f"event {masked}"
    assert parsed["ref"] == masked


@pytest.mark.parametrize(
    "value", ["109121234567", "091212345678", "۱۰۹۱۲۱۲۳۴۵۶۷", "order-0912123456"]
)
def test_numbers_adjacent_to_digits_are_not_masked(
    caplog: pytest.LogCaptureFixture, value: str
) -> None:
    output = _emit(caplog, "event", extra={"ref": value})

    assert json.loads(output)["ref"] == value


def test_bearer_and_jwt_values_are_masked_anywhere(caplog: pytest.LogCaptureFixture) -> None:
    output = _emit(
        caplog,
        "header was Bearer abc.def-123",
        extra={"header": f"bearer {JWT}", "note": f"leaked {JWT} here"},
    )

    parsed = json.loads(output)
    assert "abc.def-123" not in output
    assert JWT not in output
    assert parsed["message"] == f"header was Bearer {REDACTED}"
    assert parsed["note"] == f"leaked {REDACTED} here"


def test_non_json_values_are_masked_after_str(caplog: pytest.LogCaptureFixture) -> None:
    class Carrier:
        def __str__(self) -> str:
            return f"carrier {JWT} 09121234567"

    output = _emit(caplog, "event", extra={"obj": Carrier()})

    assert JWT not in output
    assert "09121234567" not in output


def test_exception_traceback_is_masked(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR, logger=logger.name):
        try:
            raise ValueError(f"Bearer tb-secret-1 {JWT} 09121234567")
        except ValueError:
            logger.exception("failed")
    output = JsonFormatter().format(caplog.records[-1])

    parsed = json.loads(output)
    assert "ValueError" in parsed["exception"]
    assert "tb-secret-1" not in output
    assert JWT not in output
    assert "09121234567" not in output


def test_formatter_never_raises_on_redaction_error(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(value: object) -> object:
        raise RuntimeError("redaction broke")

    monkeypatch.setattr(app_logging, "redact", boom)
    output = _emit(caplog, "event", extra={"token": "tok-must-not-leak"})

    parsed = json.loads(output)
    assert parsed["message"] == REDACTION_FAILED_MESSAGE
    assert parsed["level"] == "INFO"
    assert "tok-must-not-leak" not in output
