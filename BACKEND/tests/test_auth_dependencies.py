from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.core.errors import NotFoundError
from app.modules.auth.dependencies import ensure_owner, require_permission
from app.modules.auth.service import CurrentUser


def _user() -> CurrentUser:
    return CurrentUser(
        id=uuid4(),
        session_id=uuid4(),
        status="active",
        roles=frozenset({"customer"}),
        permissions=frozenset(),
    )


def test_ensure_owner_accepts_the_owner() -> None:
    user = _user()

    ensure_owner(user.id, user)


@pytest.mark.parametrize("owner_id", [uuid4(), None])
def test_ensure_owner_hides_foreign_or_unowned_resources_as_not_found(
    owner_id: UUID | None,
) -> None:
    with pytest.raises(NotFoundError) as caught:
        ensure_owner(owner_id, _user())

    assert caught.value.status_code == 404
    assert caught.value.code == "NOT_FOUND"


@pytest.mark.parametrize("key", ["pricing:updat", "", "PRICING:UPDATE", "admin"])
def test_require_permission_rejects_unknown_keys(key: str) -> None:
    with pytest.raises(ValueError, match="Unknown permission key"):
        require_permission(key)


def test_require_permission_accepts_a_seeded_key() -> None:
    assert callable(require_permission("pricing:update"))
