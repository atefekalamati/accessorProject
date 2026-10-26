"""Audit log writer: records a sensitive change inside the caller's transaction.

``record_audit`` only adds and flushes the row; it never commits. The audit entry is
therefore committed or rolled back together with the operation it describes.

Stored ``metadata``::

    {"actor": "user" | "system", "request_id": str | None,
     "diff": {field: {"before": ..., "after": ..., "changed": true}}}

Only changed fields appear in ``diff``, each marked ``"changed": true``. On create
(``before=None``) or delete (``after=None``) every field of the snapshot appears with
``None`` on the missing side. The diff is computed on raw values and masked afterwards
(``field_masks``, then ``app.core.redaction.redact`` for sensitive keys and phone
numbers), so a change stays visible even when both masked values look the same.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Callable, Mapping
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any, Final
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.core.redaction import redact
from app.db.models import AuditLog

ACTOR_SYSTEM: Final = "system"
ACTOR_USER: Final = "user"

# ``<entity>.<verb>``, e.g. ``product.price_changed``.
_ACTION: Final = re.compile(r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*")


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Enum):
        return _jsonable(value.value)
    if isinstance(value, UUID | Decimal):
        return str(value)
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [_jsonable(item) for item in value]
    raise TypeError(f"Audit value of type {type(value).__name__} is not JSON-serializable")


def build_diff(
    before: Mapping[str, Any] | None, after: Mapping[str, Any] | None
) -> dict[str, dict[str, Any]]:
    """Return ``{field: {"before", "after", "changed"}}`` for fields whose values differ."""
    old = _jsonable(before or {})
    new = _jsonable(after or {})
    diff: dict[str, dict[str, Any]] = {}
    for key in sorted(old.keys() | new.keys()):
        if old.get(key) != new.get(key):
            diff[key] = {"before": old.get(key), "after": new.get(key), "changed": True}
    return diff


def _mask_fields(
    diff: dict[str, dict[str, Any]], field_masks: Mapping[str, Callable[[str], str]]
) -> dict[str, dict[str, Any]]:
    for field, mask in field_masks.items():
        entry = diff.get(field)
        if entry is None:
            continue
        for side in ("before", "after"):
            if isinstance(entry[side], str):
                entry[side] = mask(entry[side])
    return diff


def client_ip(request: Request | None) -> str | None:
    if request is None or request.client is None:
        return None
    try:
        return str(ipaddress.ip_address(request.client.host))
    except ValueError:
        return None


def _request_id(request: Request | None) -> str | None:
    if request is None:
        return None
    request_id = getattr(request.state, "request_id", None)
    return None if request_id is None else str(request_id)


async def record_audit(
    session: AsyncSession,
    *,
    actor_id: UUID | None,
    action: str,
    entity_type: str,
    entity_id: UUID | None,
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    request: Request | None,
    field_masks: Mapping[str, Callable[[str], str]] | None = None,
) -> AuditLog:
    """Add an audit row to ``session`` and flush it, without committing.

    ``field_masks`` masks string values of the named fields after the diff is built,
    for personal data that ``redact`` does not cover (e.g. email).
    """
    if _ACTION.fullmatch(action) is None:
        raise ValueError(f"Audit action {action!r} must follow '<entity>.<verb>'")

    metadata = {
        "actor": ACTOR_SYSTEM if actor_id is None else ACTOR_USER,
        "request_id": _request_id(request),
        "diff": _mask_fields(build_diff(before, after), field_masks or {}),
    }
    audit_log = AuditLog(
        actor_user_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata_=redact(metadata),
        ip=client_ip(request),
    )
    session.add(audit_log)
    await session.flush()
    return audit_log
