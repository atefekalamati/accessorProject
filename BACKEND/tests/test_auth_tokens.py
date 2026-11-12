from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import uuid4

import jwt
import pytest

from app.core.config import Settings
from app.core.time import utc_now
from app.modules.auth.tokens import (
    AccessTokenError,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_refresh_token,
)


def _claims(**overrides: Any) -> dict[str, Any]:
    now = utc_now()
    claims: dict[str, Any] = {
        "sub": str(uuid4()),
        "sid": str(uuid4()),
        "typ": "access",
        "jti": uuid4().hex,
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    claims.update(overrides)
    return {key: value for key, value in claims.items() if value is not None}


def _key(settings: Settings) -> str:
    return settings.jwt_secret.get_secret_value()


def test_access_token_round_trip_carries_identity_only(settings: Settings) -> None:
    user_id, session_id = uuid4(), uuid4()
    now = utc_now()

    token = create_access_token(user_id, session_id, settings, now)
    payload = jwt.decode(token, _key(settings), algorithms=["HS256"])
    claims = decode_access_token(token, settings)

    assert (claims.user_id, claims.session_id) == (user_id, session_id)
    assert jwt.get_unverified_header(token)["alg"] == "HS256"
    assert payload["exp"] - payload["iat"] == settings.access_token_ttl_seconds
    assert not {"role", "roles", "permissions", "mobile"} & payload.keys()


@pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning")
@pytest.mark.parametrize("algorithm", ["HS512", "HS384"])
def test_other_algorithms_are_rejected(settings: Settings, algorithm: str) -> None:
    token = jwt.encode(_claims(), _key(settings), algorithm=algorithm)

    with pytest.raises(AccessTokenError):
        decode_access_token(token, settings)


def test_unsigned_token_is_rejected(settings: Settings) -> None:
    token = jwt.encode(_claims(), None, algorithm="none")

    with pytest.raises(AccessTokenError):
        decode_access_token(token, settings)


def test_token_signed_with_another_key_is_rejected(settings: Settings) -> None:
    token = jwt.encode(_claims(), "another-secret-that-is-at-least-32-chars", algorithm="HS256")

    with pytest.raises(AccessTokenError):
        decode_access_token(token, settings)


def test_expired_token_is_rejected(settings: Settings) -> None:
    past = utc_now() - timedelta(hours=1)
    token = jwt.encode(
        _claims(iat=past, exp=past + timedelta(minutes=5)), _key(settings), algorithm="HS256"
    )

    with pytest.raises(AccessTokenError):
        decode_access_token(token, settings)


@pytest.mark.parametrize("missing", ["exp", "iat", "sub", "sid", "typ", "jti"])
def test_token_missing_a_required_claim_is_rejected(settings: Settings, missing: str) -> None:
    token = jwt.encode(_claims(**{missing: None}), _key(settings), algorithm="HS256")

    with pytest.raises(AccessTokenError):
        decode_access_token(token, settings)


@pytest.mark.parametrize("overrides", [{"typ": "refresh"}, {"sub": "not-a-uuid"}])
def test_token_with_wrong_type_or_subject_is_rejected(
    settings: Settings, overrides: dict[str, Any]
) -> None:
    token = jwt.encode(_claims(**overrides), _key(settings), algorithm="HS256")

    with pytest.raises(AccessTokenError):
        decode_access_token(token, settings)


def test_garbage_is_rejected(settings: Settings) -> None:
    with pytest.raises(AccessTokenError):
        decode_access_token("not-a-jwt", settings)


def test_refresh_tokens_are_random_and_hashed() -> None:
    first, second = generate_refresh_token(), generate_refresh_token()

    assert first != second
    assert len(first) >= 43
    digest = hash_refresh_token(first)
    assert len(digest) == 64 and first not in digest
    assert digest == hash_refresh_token(first) != hash_refresh_token(second)
