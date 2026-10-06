from __future__ import annotations

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.modules.auth.otp import hash_otp_code, otp_hash_key, verify_otp_code

KEY = b"test-otp-hash-secret-at-least-32-characters"
MOBILE = "+989121234567"


def test_hash_is_deterministic_hex_digest() -> None:
    digest = hash_otp_code("012345", MOBILE, KEY)

    assert digest == hash_otp_code("012345", MOBILE, KEY)
    assert len(digest) == 64
    assert set(digest) <= set("0123456789abcdef")
    assert "012345" not in digest


@pytest.mark.parametrize(
    ("code", "mobile", "key"),
    [
        ("012346", MOBILE, KEY),
        ("012345", "+989121234568", KEY),
        ("012345", MOBILE, b"another-otp-hash-secret-of-32-characters"),
    ],
    ids=["code", "mobile", "key"],
)
def test_hash_depends_on_code_mobile_and_key(code: str, mobile: str, key: bytes) -> None:
    assert hash_otp_code(code, mobile, key) != hash_otp_code("012345", MOBILE, KEY)


def test_verify_accepts_only_the_matching_code() -> None:
    stored = hash_otp_code("000042", MOBILE, KEY)

    assert verify_otp_code("000042", MOBILE, KEY, stored)
    assert not verify_otp_code("42", MOBILE, KEY, stored)
    assert not verify_otp_code("000042", "+989121234568", KEY, stored)


def test_hash_key_comes_from_settings(settings: Settings) -> None:
    assert settings.otp_hash_secret is not None
    assert otp_hash_key(settings) == settings.otp_hash_secret.get_secret_value().encode()


def test_missing_hash_key_fails_closed(settings: Settings) -> None:
    unconfigured = settings.model_copy(update={"otp_hash_secret": None})

    with pytest.raises(RuntimeError, match="OTP_HASH_SECRET is not configured"):
        otp_hash_key(unconfigured)


def test_hash_key_is_not_the_jwt_secret(settings: Settings) -> None:
    configured = settings.model_copy(update={"otp_hash_secret": SecretStr("x" * 32)})

    assert otp_hash_key(configured) != configured.jwt_secret.get_secret_value().encode()
