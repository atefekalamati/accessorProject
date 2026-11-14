"""Guards from the security review (SEC-03): new code cannot silently skip a protection.

Each registry below lists what exists today. A new route, request field or admin write that
is not listed fails here, and whoever adds it must say how it is protected (and by which
test). The findings themselves are in docs/project/SECURITY-REVIEW.md.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

import pytest
from conftest import MakeAccount
from httpx import AsyncClient

from app.core.config import Environment, Settings
from app.main import create_app

ROOT = Path(__file__).parent.parent
API = "/api/v1"
ADMIN = f"{API}/admin"
WRITE_METHODS = frozenset({"post", "put", "patch", "delete"})


def _spec(settings: Settings) -> dict[str, Any]:
    spec: dict[str, Any] = create_app(settings).openapi()
    return spec


def _test_exists(reference: str) -> bool:
    """``file.py::test_name`` names a test function that exists."""
    file_name, _, name = reference.partition("::")
    source = (ROOT / "tests" / file_name).read_text(encoding="utf-8")
    return re.search(rf"^(async )?def {re.escape(name)}\(", source, re.M) is not None


# --- 1. every request body refuses unknown fields (mass assignment) ------------------------


def _refs(schema: dict[str, Any]) -> list[str]:
    found: list[str] = []
    if "$ref" in schema:
        found.append(schema["$ref"].split("/")[-1])
    for key in ("anyOf", "allOf", "oneOf"):
        for item in schema.get(key, []):
            found.extend(_refs(item))
    if "items" in schema:
        found.extend(_refs(schema["items"]))
    for item in schema.get("prefixItems", []):
        found.extend(_refs(item))
    if isinstance(schema.get("additionalProperties"), dict):  # dict[str, Model]
        found.extend(_refs(schema["additionalProperties"]))
    return found


def test_every_json_request_schema_forbids_unknown_fields_at_every_level(
    settings: Settings,
) -> None:
    spec = _spec(settings)
    schemas = spec["components"]["schemas"]
    pending = [
        name
        for item in spec["paths"].values()
        for method, operation in item.items()
        if method in WRITE_METHODS
        for name in _refs(
            operation.get("requestBody", {})
            .get("content", {})
            .get("application/json", {})
            .get("schema", {})
        )
    ]
    seen: set[str] = set()
    open_schemas: list[str] = []
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        schema = schemas[name]
        if schema.get("type") == "object" or "properties" in schema:
            if schema.get("additionalProperties") is not False:
                open_schemas.append(name)
            for field in schema.get("properties", {}).values():
                pending.extend(_refs(field))

    assert seen, "no request schemas found"
    assert open_schemas == []


@pytest.mark.integration
@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("PATCH", "/users/me", {"roles": ["super_admin"]}),
        ("PATCH", "/users/me", {"status": "active"}),
        ("PATCH", "/users/me", {"phone": "+989120000000"}),
        ("PATCH", "/users/me", {"permissions": ["users:manage_roles"]}),
    ],
)
async def test_a_customer_cannot_send_privileged_fields(
    auth_client: AsyncClient, make_account: MakeAccount, method: str, path: str, body: Any
) -> None:
    customer = await make_account("customer")

    response = await auth_client.request(method, API + path, json=body, headers=customer.headers)

    assert response.status_code == 400, response.text
    me = await auth_client.get(f"{API}/auth/me", headers=customer.headers)
    assert me.json()["roles"] == ["customer"]


# --- 2. every id a customer sends is ownership- or visibility-checked (IDOR) ---------------

OWNERSHIP = "test_account_ownership.py::test_another_customers_resources_are_404_and_untouched"
_RETURN_OWNERSHIP = "test_returns.py::test_auth_and_ownership"
# Path parameters of non-admin routes: how each is protected, and the test that proves it.
PATH_PARAMETERS: dict[tuple[str, str], str] = {
    ("GET", "/categories/{slug}"): "public",
    ("GET", "/categories/{slug}/filters"): "public",
    ("GET", "/categories/{slug}/products"): "public",
    ("GET", "/products/{slug}"): "public",
    ("GET", "/products/{product_id}/pricing"): "public",
    ("GET", "/products/{product_id}/availability"): "public",
    ("GET", "/pages/{slug}"): "public",
    ("PATCH", "/cart/items/{item_id}"): OWNERSHIP,
    ("DELETE", "/cart/items/{item_id}"): OWNERSHIP,
    ("GET", "/addresses/{address_id}"): OWNERSHIP,
    ("PATCH", "/addresses/{address_id}"): OWNERSHIP,
    ("DELETE", "/addresses/{address_id}"): OWNERSHIP,
    ("GET", "/orders/{order_number}"): OWNERSHIP,
    ("POST", "/orders/{order_id}/cancel"): OWNERSHIP,
    ("POST", "/orders/{order_number}/returns"): _RETURN_OWNERSHIP,
    ("GET", "/returns/{return_id}"): _RETURN_OWNERSHIP,
    ("POST", "/returns/{return_id}/cancel"): _RETURN_OWNERSHIP,
    # Development and CI only; never mounted in production (test below).
    ("GET", "/payments/fake/{reference}"): "dev-only",
    ("POST", "/payments/fake/{reference}/complete"): "dev-only",
}
# Ids inside request bodies of non-admin routes.
BODY_IDS: dict[tuple[str, str, str], str] = {
    ("POST", "/cart/items", "variant_id"): (
        "test_cart_items.py::test_hidden_variants_are_404_and_unsellable_ones_422"
    ),
    ("POST", "/checkout/validate", "address_id"): OWNERSHIP,
    ("POST", "/checkout/validate", "shipping_method_id"): (
        "test_checkout_validate.py::test_errors_in_check_order"
    ),
    (
        "POST",
        "/orders",
        "address_id",
    ): "test_orders_create.py::test_business_errors_leave_nothing_behind",
    ("POST", "/orders", "shipping_method_id"): (
        "test_orders_create.py::test_business_errors_leave_nothing_behind"
    ),
    ("POST", "/payments/init", "order_id"): OWNERSHIP,
    ("POST", "/orders/{order_number}/returns", "order_item_id"): (
        "test_returns.py::test_quantity_rules"
    ),
}
# Ids in query strings of non-admin routes.
QUERY_IDS: dict[tuple[str, str, str], str] = {
    ("GET", "/products/{product_id}/pricing", "variant_id"): "public",
    ("GET", "/products/{product_id}/availability", "variant_id"): "public",
}
# A field or parameter that carries an id: ``id``, ``*_id`` or ``*_ids``.
_ID_NAME = re.compile(r"^id$|_ids?$")


def _properties(schemas: dict[str, Any], name: str, seen: set[str]) -> set[str]:
    if name in seen:
        return set()
    seen.add(name)
    found: set[str] = set()
    for field, schema in schemas[name].get("properties", {}).items():
        found.add(field)
        for ref in _refs(schema):
            found |= _properties(schemas, ref, seen)
    return found


def test_every_customer_route_id_is_classified(settings: Settings) -> None:
    spec = _spec(settings)
    schemas = spec["components"]["schemas"]
    paths: set[tuple[str, str]] = set()
    bodies: set[tuple[str, str, str]] = set()
    queries: set[tuple[str, str, str]] = set()
    for path, item in spec["paths"].items():
        if path.startswith(ADMIN):
            continue
        short = path.removeprefix(API)
        for method, operation in item.items():
            if method not in WRITE_METHODS | {"get"}:
                continue
            if "{" in path:
                paths.add((method.upper(), short))
            for parameter in operation.get("parameters", []):
                if parameter.get("in") == "query" and _ID_NAME.search(parameter["name"]):
                    queries.add((method.upper(), short, parameter["name"]))
            body = operation.get("requestBody", {}).get("content", {}).get("application/json")
            for ref in _refs(body["schema"]) if body else []:
                for field in _properties(schemas, ref, set()):
                    if _ID_NAME.search(field):
                        bodies.add((method.upper(), short, field))

    assert paths == set(PATH_PARAMETERS)
    assert bodies == set(BODY_IDS)
    assert queries == set(QUERY_IDS)
    references = {*PATH_PARAMETERS.values(), *BODY_IDS.values(), *QUERY_IDS.values()}
    for reference in references - {"public", "dev-only"}:
        assert _test_exists(reference), reference


def test_dev_routes_are_absent_in_production(settings: Settings) -> None:
    development = {path for path in _spec(settings)["paths"] if "/dev/" in path or "/fake" in path}
    production = create_app(settings.model_copy(update={"environment": Environment.PRODUCTION}))
    mounted = {getattr(route, "path", "") for route in production.routes}

    assert development  # the dev routes exist outside production
    assert not {path for path in mounted if "/dev/" in path or "/fake" in path}


# --- 3. every admin write is audited --------------------------------------------------------

AUDITED_ADMIN_WRITES: dict[tuple[str, str], tuple[str, ...]] = {
    ("PATCH", "/users/{user_id}/status"): ("user.status_changed",),
    ("PATCH", "/users/{user_id}/role"): ("user.roles_changed",),
    ("POST", "/categories"): ("category.created",),
    ("PATCH", "/categories/{category_id}"): ("category.updated",),
    ("DELETE", "/categories/{category_id}"): ("category.deleted",),
    ("PATCH", "/categories/{category_id}/filters"): ("category.filters_updated",),
    ("POST", "/products"): ("product.created",),
    ("PATCH", "/products/{product_id}"): ("product.updated",),
    ("DELETE", "/products/{product_id}"): ("product.deleted",),
    ("PATCH", "/products/{product_id}/status"): ("product.status_changed",),
    ("POST", "/products/{product_id}/variants"): ("product_variant.created",),
    ("PATCH", "/product-variants/{variant_id}"): ("product_variant.updated",),
    ("DELETE", "/product-variants/{variant_id}"): ("product_variant.deleted",),
    ("POST", "/products/{product_id}/media"): ("product_media.created",),
    ("PATCH", "/products/{product_id}/media/{media_id}"): ("product_media.updated",),
    ("DELETE", "/products/{product_id}/media/{media_id}"): ("product_media.deleted",),
    ("POST", "/media"): ("media.uploaded",),
    ("PATCH", "/pricing/settings"): ("pricing.settings_updated",),
    ("PATCH", "/product-variants/{variant_id}/price"): ("product_variant.price_changed",),
    ("PATCH", "/products/{product_id}/price"): ("product_variant.price_changed",),
    ("PATCH", "/inventory/{variant_id}"): ("inventory.adjusted", "inventory.threshold_updated"),
    ("POST", "/discounts"): ("discount.created",),
    ("PATCH", "/discounts/{code_id}"): ("discount.updated",),
    ("DELETE", "/discounts/{code_id}"): ("discount.deleted",),
    ("POST", "/shipping-methods"): ("shipping_method.created",),
    ("PATCH", "/shipping-methods/{method_id}"): ("shipping_method.updated",),
    ("DELETE", "/shipping-methods/{method_id}"): ("shipping_method.deleted",),
    ("PATCH", "/orders/{order_id}/shipment"): ("shipment.updated", "order.status_changed"),
    ("POST", "/orders/{order_id}/cancel"): ("order.status_changed",),
    ("POST", "/payments/{payment_id}/refund"): ("payment.refunded",),
    ("POST", "/pages"): ("static_page.created",),
    ("PATCH", "/pages/{page_id}"): ("static_page.updated",),
    ("DELETE", "/pages/{page_id}"): ("static_page.deleted",),
    ("POST", "/faq"): ("faq_item.created",),
    ("PATCH", "/faq/{item_id}"): ("faq_item.updated",),
    ("DELETE", "/faq/{item_id}"): ("faq_item.deleted",),
    ("PATCH", "/contact-messages/{message_id}"): ("contact_message.updated",),
    ("POST", "/home/sections"): ("home_section.created",),
    ("PATCH", "/home/sections/{section_id}"): ("home_section.updated",),
    ("DELETE", "/home/sections/{section_id}"): ("home_section.deleted",),
    ("POST", "/banners"): ("banner.created",),
    ("PATCH", "/banners/{banner_id}"): ("banner.updated",),
    ("DELETE", "/banners/{banner_id}"): ("banner.deleted",),
}


# Writes whose endpoint calls a service of another package, which records the audit.
AUDIT_PACKAGES: dict[tuple[str, str], str] = {
    ("POST", "/payments/{payment_id}/refund"): "app/modules/payments",
}


def _string_constants(package: Path) -> set[str]:
    """String literals in code under ``package``: not comments, not docstrings."""
    found: set[str] = set()
    for path in package.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = {
            id(node.value)
            for node in ast.walk(tree)
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
        }
        found |= {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        }
    return found


def _endpoints(routes: Any, prefix: str) -> list[tuple[str, set[str], Any]]:
    """``(full path, methods, endpoint)`` of every route, through included routers."""
    found: list[tuple[str, set[str], Any]] = []
    for route in routes:
        included = getattr(route, "original_router", None)
        if included is not None:
            context = getattr(route, "include_context", None)
            found += _endpoints(included.routes, prefix + getattr(context, "prefix", ""))
        elif getattr(route, "endpoint", None) is not None:
            found.append(
                (prefix + route.path, set(getattr(route, "methods", set())), route.endpoint)
            )
    return found


def test_every_admin_write_names_the_audit_actions_it_records(settings: Settings) -> None:
    """Each admin write's audit actions are code literals in the package of its endpoint."""
    packages: dict[tuple[str, str], Path] = {}
    for full_path, methods, endpoint in _endpoints(create_app(settings).routes, ""):
        if not full_path.startswith(f"{ADMIN}/"):
            continue
        package = ROOT.joinpath(*endpoint.__module__.split(".")[:-1])
        for method in methods:
            if method.lower() in WRITE_METHODS:
                route = (method, full_path.removeprefix(ADMIN))
                override = AUDIT_PACKAGES.get(route)
                packages[route] = ROOT / override if override else package

    assert set(packages) == set(AUDITED_ADMIN_WRITES)
    literals = {package: _string_constants(package) for package in set(packages.values())}
    for route, actions in AUDITED_ADMIN_WRITES.items():
        for action in actions:
            assert action in literals[packages[route]], (route, action)


# --- 4. deployment config never trusts every proxy --------------------------------------------


def test_no_config_trusts_forwarded_headers_from_everyone() -> None:
    files = [
        ROOT / "Dockerfile",
        ROOT / ".env.example",
        *ROOT.glob("docker-compose*.yml"),
        *ROOT.glob("scripts/*.sh"),
        *(ROOT.parent / ".github" / "workflows").glob("*.yml"),
    ]
    trusts_everyone = re.compile(r"forwarded[-_]allow[-_]ips['\"]?[\s=:,]*['\"]?\*", re.I)
    for path in files:
        assert not trusts_everyone.search(path.read_text(encoding="utf-8")), path.name


def test_the_proxy_guard_catches_every_spelling() -> None:
    pattern = re.compile(r"forwarded[-_]allow[-_]ips['\"]?[\s=:,]*['\"]?\*", re.I)
    for text in (
        "FORWARDED_ALLOW_IPS=*",
        'FORWARDED_ALLOW_IPS: "*"',
        "--forwarded-allow-ips=*",
        '"--forwarded-allow-ips", "*"',
    ):
        assert pattern.search(text), text
    assert not pattern.search("FORWARDED_ALLOW_IPS=10.0.0.5")
