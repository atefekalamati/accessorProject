from __future__ import annotations

import re

from app.db.seed import ALL_PERMISSION_KEYS, DEFAULT_ROLES, PERMISSIONS, ROLE_PERMISSIONS

PERMISSION_KEY = re.compile(r"^[a-z_]+:[a-z_]+$")


def test_roles_match_adr_004() -> None:
    assert {role.name for role in DEFAULT_ROLES} == {
        "customer",
        "support",
        "content_manager",
        "admin",
        "super_admin",
    }


def test_permission_keys_are_unique_and_well_formed() -> None:
    keys = [permission.key for permission in PERMISSIONS]
    assert len(keys) == len(set(keys))
    assert all(PERMISSION_KEY.fullmatch(key) for key in keys)
    assert {"pricing:update", "inventory:update", "users:manage_roles"} <= set(keys)


def test_every_role_is_mapped_to_known_permissions() -> None:
    assert set(ROLE_PERMISSIONS) == {role.name for role in DEFAULT_ROLES}
    for keys in ROLE_PERMISSIONS.values():
        assert keys <= ALL_PERMISSION_KEYS


def test_role_permission_boundaries() -> None:
    assert ROLE_PERMISSIONS["super_admin"] == ALL_PERMISSION_KEYS
    assert ROLE_PERMISSIONS["customer"] == frozenset()
    admin = ROLE_PERMISSIONS["admin"]
    assert "inventory:update" in admin
    assert not admin & {"users:manage_roles", "pricing_settings:update", "audit:read"}
