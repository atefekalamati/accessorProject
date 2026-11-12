from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.models import User


def test_new_row_is_not_deleted() -> None:
    user = User(phone="+989121234567")

    assert user.deleted_at is None
    assert user.is_deleted is False


def test_soft_delete_sets_utc_deleted_at() -> None:
    user = User(phone="+989121234567")

    user.soft_delete()

    assert user.is_deleted is True
    assert user.deleted_at is not None
    assert user.deleted_at.utcoffset() == timedelta(0)


def test_soft_delete_is_idempotent() -> None:
    first_deleted_at = datetime(2026, 1, 1, tzinfo=UTC)
    user = User(phone="+989121234567", deleted_at=first_deleted_at)

    user.soft_delete()
    user.soft_delete()

    assert user.deleted_at == first_deleted_at
