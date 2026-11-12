"""Five roles × every ``/admin`` route (ADM-07, PRD «هویت و دسترسی» ✓, ADR-018, ADR-019).

``MATRIX`` names, for each admin route, the permissions that let a caller past
authorization (any of them). Routes are discovered from the app, so a new admin route
without a row fails. Each role must then get exactly: no token → 401, a role without one
of the permissions → 403, a role with one → anything but 401/403 (the requests carry
random ids and empty bodies, so they stop at 400/404 and change nothing).
"""

from __future__ import annotations

from typing import Any, Final
from uuid import uuid4

import pytest
from conftest import MakeAccount
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import Permission, Role, RolePermission
from app.db.seed import ALL_PERMISSION_KEYS, ROLE_PERMISSIONS

API: Final = "/api/v1"

CATALOG = frozenset({"catalog:manage"})
CATEGORY_CONTENT = frozenset({"catalog:manage", "categories:edit_content"})
INVENTORY_READ = frozenset({"inventory:read", "inventory:update"})


def _one(key: str) -> frozenset[str]:
    return frozenset({key})


MATRIX: Final[dict[tuple[str, str], frozenset[str]]] = {
    # users and roles (AUTH-11)
    ("GET", "/admin/users"): _one("users:read"),
    ("PATCH", "/admin/users/{user_id}/status"): _one("users:manage"),
    ("PATCH", "/admin/users/{user_id}/role"): _one("users:manage_roles"),
    # customers (ADM-03), audit log (ADM-06), dashboard and reports (ADM-04, ADM-05)
    ("GET", "/admin/customers"): _one("customers:read"),
    ("GET", "/admin/customers/{user_id}"): _one("customers:read"),
    ("GET", "/admin/audit-logs"): _one("audit:read"),
    ("GET", "/admin/dashboard"): _one("reports:read"),
    ("GET", "/admin/reports/sales"): _one("reports:read"),
    ("GET", "/admin/reports/products"): _one("reports:read"),
    ("GET", "/admin/reports/categories"): _one("reports:read"),
    # categories (CAT-09, CAT-10) and media (CAT-05)
    ("GET", "/admin/categories"): CATEGORY_CONTENT,
    ("POST", "/admin/categories"): CATALOG,
    ("PATCH", "/admin/categories/{category_id}"): CATEGORY_CONTENT,
    ("DELETE", "/admin/categories/{category_id}"): CATALOG,
    ("PATCH", "/admin/categories/{category_id}/filters"): CATALOG,
    ("POST", "/admin/media"): CATEGORY_CONTENT,
    # products, variants and product media (CAT-11)
    ("GET", "/admin/products"): CATALOG,
    ("GET", "/admin/products/{product_id}"): CATALOG,
    ("POST", "/admin/products"): CATALOG,
    ("PATCH", "/admin/products/{product_id}"): CATALOG,
    ("PATCH", "/admin/products/{product_id}/status"): CATALOG,
    ("DELETE", "/admin/products/{product_id}"): CATALOG,
    ("POST", "/admin/products/{product_id}/variants"): CATALOG,
    ("PATCH", "/admin/product-variants/{variant_id}"): CATALOG,
    ("DELETE", "/admin/product-variants/{variant_id}"): CATALOG,
    ("POST", "/admin/products/{product_id}/media"): CATALOG,
    ("PATCH", "/admin/products/{product_id}/media/{media_id}"): CATALOG,
    ("DELETE", "/admin/products/{product_id}/media/{media_id}"): CATALOG,
    # pricing (PRC-03, PRC-05)
    ("GET", "/admin/pricing/settings"): _one("pricing_settings:update"),
    ("PATCH", "/admin/pricing/settings"): _one("pricing_settings:update"),
    ("PATCH", "/admin/product-variants/{variant_id}/price"): _one("pricing:update"),
    ("PATCH", "/admin/products/{product_id}/price"): _one("pricing:update"),
    ("GET", "/admin/products/{product_id}/price-history"): frozenset(
        {"catalog:manage", "pricing:update"}
    ),
    # inventory (INV-02, INV-08)
    ("GET", "/admin/inventory"): INVENTORY_READ,
    ("GET", "/admin/inventory/reservations"): INVENTORY_READ,
    ("PATCH", "/admin/inventory/{variant_id}"): _one("inventory:update"),
    ("GET", "/admin/inventory/{variant_id}/history"): INVENTORY_READ,
    # discount codes (DSC-04) and shipping methods (ADDR-03)
    ("GET", "/admin/discounts"): _one("discounts:manage"),
    ("GET", "/admin/discounts/{code_id}"): _one("discounts:manage"),
    ("POST", "/admin/discounts"): _one("discounts:manage"),
    ("PATCH", "/admin/discounts/{code_id}"): _one("discounts:manage"),
    ("DELETE", "/admin/discounts/{code_id}"): _one("discounts:manage"),
    ("GET", "/admin/shipping-methods"): _one("shipping:manage"),
    ("GET", "/admin/shipping-methods/{method_id}"): _one("shipping:manage"),
    ("POST", "/admin/shipping-methods"): _one("shipping:manage"),
    ("PATCH", "/admin/shipping-methods/{method_id}"): _one("shipping:manage"),
    ("DELETE", "/admin/shipping-methods/{method_id}"): _one("shipping:manage"),
    # orders, shipments, payments and refunds (ADM-01, ADM-02, ADM-08)
    ("GET", "/admin/orders"): _one("orders:read"),
    ("GET", "/admin/orders/{order_id}"): _one("orders:read"),
    ("PATCH", "/admin/orders/{order_id}/shipment"): _one("orders:update_status"),
    ("POST", "/admin/orders/{order_id}/cancel"): _one("orders:update_status"),
    ("GET", "/admin/payments"): _one("orders:read"),
    ("POST", "/admin/payments/{payment_id}/refund"): _one("payments:refund"),
    # static pages (CNT-04)
    ("GET", "/admin/pages"): _one("content:manage"),
    ("POST", "/admin/pages"): _one("content:manage"),
    ("PATCH", "/admin/pages/{page_id}"): _one("content:manage"),
    ("DELETE", "/admin/pages/{page_id}"): _one("content:manage"),
    # FAQ (CNT-05)
    ("GET", "/admin/faq"): _one("content:manage"),
    ("POST", "/admin/faq"): _one("content:manage"),
    ("PATCH", "/admin/faq/{item_id}"): _one("content:manage"),
    ("DELETE", "/admin/faq/{item_id}"): _one("content:manage"),
    # home sections (CNT-02)
    ("GET", "/admin/home/sections"): _one("content:manage"),
    ("POST", "/admin/home/sections"): _one("content:manage"),
    ("PATCH", "/admin/home/sections/{section_id}"): _one("content:manage"),
    ("DELETE", "/admin/home/sections/{section_id}"): _one("content:manage"),
    # contact messages (CNT-06)
    ("GET", "/admin/contact-messages"): _one("contact_messages:manage"),
    ("GET", "/admin/contact-messages/{message_id}"): _one("contact_messages:manage"),
    ("PATCH", "/admin/contact-messages/{message_id}"): _one("contact_messages:manage"),
}

# The seed mapping, written out independently (PRD «هویت و دسترسی» ✓, ADR-019, D35).
EXPECTED_ROLES: Final[dict[str, frozenset[str]]] = {
    "customer": frozenset(),
    "support": frozenset({"orders:read", "customers:read", "contact_messages:manage"}),
    "content_manager": frozenset({"content:manage", "categories:edit_content"}),
    "admin": ALL_PERMISSION_KEYS - {"pricing_settings:update", "users:manage_roles", "audit:read"},
    "super_admin": ALL_PERMISSION_KEYS,
}

# Required query parameters, so an allowed caller is not stopped by validation alone.
QUERY: Final[dict[str, dict[str, str]]] = {
    "/admin/reports/sales": {"from": "2024-01-01", "to": "2024-01-02"},
    "/admin/reports/products": {"from": "2024-01-01", "to": "2024-01-02"},
    "/admin/reports/categories": {"from": "2024-01-01", "to": "2024-01-02"},
}


def test_matrix_covers_every_admin_route(client: AsyncClient) -> None:
    app = client._transport.app  # type: ignore[attr-defined]
    routes = {
        (method.upper(), path.removeprefix(API))
        for path, operations in app.openapi()["paths"].items()
        if path.startswith(f"{API}/admin")
        for method in operations
    }

    assert routes == set(MATRIX)
    assert set().union(*MATRIX.values()) <= ALL_PERMISSION_KEYS


def test_seeded_roles_have_exactly_the_expected_permissions() -> None:
    assert dict(ROLE_PERMISSIONS) == EXPECTED_ROLES


@pytest.mark.integration
async def test_the_database_holds_the_seeded_role_permissions(
    auth_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    """``auth_client`` runs ``seed_rbac``; the rows must match the mapping exactly."""
    async with AsyncSession(db_engine) as session:
        rows = await session.execute(
            select(Role.name, Permission.key)
            .join(RolePermission, RolePermission.role_id == Role.id)
            .join(Permission, Permission.id == RolePermission.permission_id)
        )
        stored: dict[str, set[str]] = {}
        for role, key in rows:
            stored.setdefault(role, set()).add(key)

    for role, keys in EXPECTED_ROLES.items():
        assert stored.get(role, set()) == keys, role


async def _call(client: AsyncClient, method: str, path: str, headers: dict[str, str] | None) -> Any:
    url = API + path.format_map({name: uuid4() for name in _params(path)})
    body: dict[str, Any] | None = {} if method in {"POST", "PATCH"} else None
    return await client.request(method, url, json=body, params=QUERY.get(path), headers=headers)


def _params(path: str) -> list[str]:
    return [part[1:-1] for part in path.split("/") if part.startswith("{")]


@pytest.mark.integration
async def test_every_role_on_every_admin_route(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    accounts = {role: await make_account(role) for role in EXPECTED_ROLES}
    problems: list[str] = []
    for (method, path), allowed in sorted(MATRIX.items()):
        anonymous = await _call(auth_client, method, path, None)
        if anonymous.status_code != 401:
            problems.append(f"{method} {path} anonymous → {anonymous.status_code}")
        for role, account in accounts.items():
            response = await _call(auth_client, method, path, account.headers)
            if EXPECTED_ROLES[role] & allowed:
                if response.status_code in (401, 403):
                    problems.append(f"{method} {path} {role} → {response.status_code}")
            elif response.status_code != 403 or response.json()["error"]["code"] != "FORBIDDEN":
                problems.append(f"{method} {path} {role} → {response.status_code}, want 403")

    assert problems == []
