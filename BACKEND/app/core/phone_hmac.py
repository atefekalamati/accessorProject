"""Keyed digest of a mobile number, so the per-customer discount limit needs no raw phone.

DSC-06, ADR-063 A2. ``PHONE_HMAC_KEYS`` lists ``id:secret`` pairs, newest first:
the first key writes new digests, every key is used to count old ones, so rotating a key
keeps the "once per customer" limit (runbook: docs/ops/PHONE-HMAC-KEYS.md). The digest
survives account deletion (ACC-05): re-registering with the same number still counts.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass, field
from typing import Final

KEY_ID_PATTERN: Final = r"^[a-z0-9][a-z0-9_-]{0,15}$"
DIGEST_PATTERN: Final = r"^[0-9a-f]{64}$"
MIN_SECRET_LENGTH: Final = 32
_KEY_ID = re.compile(KEY_ID_PATTERN)


@dataclass(frozen=True, slots=True)
class PhoneKey:
    key_id: str
    # Never in a repr, log line or traceback frame.
    secret: bytes = field(repr=False)

    def digest(self, phone: str) -> str:
        """HMAC-SHA256 of the normalized (E.164) mobile, as 64 hex characters."""
        return hmac.new(self.secret, phone.encode(), hashlib.sha256).hexdigest()


@dataclass(frozen=True, slots=True)
class PhoneKeys:
    keys: tuple[PhoneKey, ...]

    @property
    def write(self) -> PhoneKey:
        return self.keys[0]

    def get(self, key_id: str) -> PhoneKey | None:
        return next((key for key in self.keys if key.key_id == key_id), None)

    def digests(self, phone: str) -> list[tuple[str, str]]:
        """``(key id, digest)`` of ``phone`` under every key: what the count matches."""
        return [(key.key_id, key.digest(phone)) for key in self.keys]


def parse_phone_keys(value: str) -> PhoneKeys:
    """``"k2:secret2,k1:secret1"`` → keys, newest first. Raises ``ValueError`` if invalid."""
    keys: list[PhoneKey] = []
    for part in value.split(","):
        key_id, sep, secret = part.strip().partition(":")
        if not sep or not _KEY_ID.fullmatch(key_id):
            raise ValueError("each PHONE_HMAC_KEYS entry is id:secret with a short lowercase id")
        if len(secret) < MIN_SECRET_LENGTH:
            raise ValueError(f"each PHONE_HMAC_KEYS secret needs {MIN_SECRET_LENGTH}+ chars")
        if any(key.key_id == key_id for key in keys):
            raise ValueError("PHONE_HMAC_KEYS ids must be unique")
        keys.append(PhoneKey(key_id, secret.encode()))
    if not keys:
        raise ValueError("PHONE_HMAC_KEYS needs at least one key")
    return PhoneKeys(tuple(keys))
