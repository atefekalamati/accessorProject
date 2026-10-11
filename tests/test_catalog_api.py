"""Catalog API error coverage and end-to-end flow (CAT-12).

``COVERAGE`` maps every catalog endpoint and every status in ``STATUSES`` to the test that
exercises it (``module::test``), or to ``n/a: <reason>`` when the status cannot happen.
Two guards keep it honest: the map must match the real routes, and every named test must
exist. Gaps found while building the map are tested in this file.
"""

from __future__ import annotations

import ast
import io
from functools import cache
from pathlib import Path
from typing import Any, Final
from uuid import UUID, uuid4

import pytest
from conftest import Catalog, MakeAccount
from httpx import AsyncClient, Response
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import InventoryItem
from app.db.models.inventory import DEFAULT_WAREHOUSE_ID

API = "/api/v1"
STATUSES: Final = (400, 401, 403, 404, 409, 422)
CATALOG_PREFIXES: Final = (
    f"{API}/categories",
    f"{API}/products",
    f"{API}/admin/categories",
    f"{API}/admin/products",
    f"{API}/admin/product-variants",
    f"{API}/admin/media",
)

PUBLIC = "n/a: public endpoint, no authentication or permission"
READ_ONLY = "n/a: read-only, no state to conflict with"
NO_RULE = "n/a: no business rule beyond the request validation"
COLLECTION = "n/a: collection endpoint, nothing to look up"
SOFT_DELETE = "n/a: a referenced row is soft deleted, never blocked"

AUTH_PRODUCTS = "test_admin_products::test_endpoints_need_authentication_before_validation"
PERM_PRODUCTS = "test_admin_products::test_endpoints_need_catalog_manage"
AUTH_CATEGORIES = "test_admin_categories::test_every_endpoint_requires_authentication"
PERM_CATEGORIES = "test_admin_categories::test_roles_without_category_permissions_get_403"
MALFORMED_ID = "test_catalog_api::test_malformed_ids_are_400"


def _public(**cells: str) -> dict[int, str]:
    return {401: PUBLIC, 403: PUBLIC, 409: READ_ONLY, 422: READ_ONLY} | {
        int(key[1:]): value for key, value in cells.items()
    }


def _products(**cells: str) -> dict[int, str]:
    return {401: AUTH_PRODUCTS, 403: PERM_PRODUCTS} | {
        int(key[1:]): value for key, value in cells.items()
    }


def _categories(**cells: str) -> dict[int, str]:
    return {401: AUTH_CATEGORIES, 403: PERM_CATEGORIES} | {
        int(key[1:]): value for key, value in cells.items()
    }


COVERAGE: Final[dict[tuple[str, str], dict[int, str]]] = {
    # --- public ---------------------------------------------------------------------
    ("GET", "/categories"): _public(
        s400="test_categories_public::test_unknown_query_parameter_is_400",
        s404=COLLECTION,
    ),
    ("GET", "/categories/{slug}"): _public(
        s400="test_catalog_api::test_public_reads_reject_unknown_query_parameters",
        s404="test_categories_public::test_detail_of_hidden_category_is_404",
    ),
    ("GET", "/categories/{slug}/filters"): _public(
        s400="test_category_filters::test_filters_reject_unknown_query_params",
        s404="test_category_filters::test_filters_of_hidden_category_are_404",
    ),
    ("GET", "/categories/{slug}/products"): _public(
        s400="test_products_list::test_invalid_query_is_400",
        s404="test_products_list::test_hidden_or_unknown_category_is_404",
        s422="test_products_list::test_filter_not_in_category_is_422",
    ),
    ("GET", "/products"): _public(
        s400="test_products_list::test_invalid_query_is_400",
        s404="test_products_list::test_hidden_or_unknown_category_is_404",
        s422="test_products_list::test_all_products_listing_spans_categories",
    ),
    ("GET", "/products/{slug}"): _public(
        s400="test_products_public::test_invalid_slug_is_400",
        s404="test_products_public::test_hidden_products_get_the_same_404",
    ),
    ("GET", "/products/{product_id}/pricing"): _public(
        s400="test_product_pricing::test_invalid_request_is_400",
        s404="test_product_pricing::test_hidden_products_and_variants_are_404",
    ),
    ("GET", "/products/{product_id}/availability"): _public(
        s400="test_product_availability::test_invalid_request_is_400",
        s404="test_product_availability::test_hidden_products_and_variants_are_404",
    ),
    # --- admin categories -------------------------------------------------------------
    ("GET", "/admin/categories"): _categories(
        s400="test_admin_categories::test_invalid_list_query_is_400",
        s404=COLLECTION,
        s409=READ_ONLY,
        s422=READ_ONLY,
    ),
    ("POST", "/admin/categories"): _categories(
        s400="test_admin_categories::test_invalid_create_body_is_400",
        s404="n/a: a missing or deleted parent is 422 (ADR-025)",
        s409="test_admin_categories::test_duplicate_slug_is_409",
        s422="test_admin_categories::test_missing_or_deleted_parent_is_422",
    ),
    ("PATCH", "/admin/categories/{category_id}"): _categories(
        s400="test_admin_categories::test_invalid_patch_body_is_400",
        s404="test_admin_categories::test_patch_unknown_or_deleted_category_is_404",
        s409="test_admin_categories::test_cycles_are_409",
        s422="test_admin_categories::test_depth_limit_counts_moved_subtree",
    ),
    ("DELETE", "/admin/categories/{category_id}"): _categories(
        s400=MALFORMED_ID,
        s404="test_admin_categories::test_delete_soft_deletes_with_audit",
        s409="test_admin_categories::test_delete_with_children_or_products_is_409",
        s422="n/a: a category in use is 409 (ADR-025)",
    ),
    ("PATCH", "/admin/categories/{category_id}/filters"): {
        400: "test_category_filters::test_invalid_filter_set_is_400",
        401: "test_category_filters::test_filters_need_authentication",
        403: "test_category_filters::test_filters_need_catalog_manage",
        404: "test_category_filters::test_unknown_or_deleted_category_is_404",
        409: "n/a: the whole set is replaced; duplicate keys in the body are 400",
        422: "n/a: an invalid key/type pairing is 400 (ADR-026)",
    },
    # --- admin products ---------------------------------------------------------------
    ("GET", "/admin/products"): _products(
        s400="test_admin_products::test_list_validation",
        s404=COLLECTION,
        s409=READ_ONLY,
        s422=READ_ONLY,
    ),
    ("GET", "/admin/products/{product_id}"): _products(
        s400="test_admin_products::test_get_missing_product",
        s404="test_admin_products::test_get_missing_product",
        s409=READ_ONLY,
        s422=READ_ONLY,
    ),
    ("POST", "/admin/products"): _products(
        s400="test_admin_products::test_create_product_validation",
        s404="test_admin_products::test_create_product_in_missing_or_deleted_category",
        s409="test_admin_products::test_create_product_with_duplicate_slug",
        s422="n/a: a new product is always a draft, without publish rules",
    ),
    ("PATCH", "/admin/products/{product_id}"): _products(
        s400="test_admin_products::test_update_product_validation",
        s404="test_admin_products::test_update_product_conflicts_and_missing",
        s409="test_admin_products::test_update_product_conflicts_and_missing",
        s422="n/a: status changes go through PATCH .../status (400 here)",
    ),
    ("PATCH", "/admin/products/{product_id}/status"): _products(
        s400="test_admin_products::test_invalid_transitions",
        s404="test_admin_products::test_invalid_transitions",
        s409="n/a: concurrent changes wait on the product row lock (ADR-030)",
        s422="test_admin_products::test_publish_blockers",
    ),
    ("DELETE", "/admin/products/{product_id}"): _products(
        s400=MALFORMED_ID,
        s404="test_admin_products::test_delete_product_soft_deletes_it_and_its_variants",
        s409=SOFT_DELETE,
        s422=SOFT_DELETE,
    ),
    ("POST", "/admin/products/{product_id}/variants"): _products(
        s400="test_admin_products::test_create_variant_validation",
        s404="test_admin_products::test_create_variant_rules",
        s409="test_admin_products::test_create_variant_rules",
        s422="test_admin_products::test_create_variant_rules",
    )
    | {403: "test_admin_products::test_initial_price_needs_pricing_update"},
    ("PATCH", "/admin/product-variants/{variant_id}"): _products(
        s400="test_admin_products::test_update_variant_rules",
        s404="test_admin_products::test_update_variant_rules",
        s409="test_admin_products::test_update_variant_rules",
        s422="test_admin_products::test_update_variant_rules",
    ),
    ("DELETE", "/admin/product-variants/{variant_id}"): _products(
        s400=MALFORMED_ID,
        s404="test_admin_products::test_delete_variant_detaches_its_images",
        s409=SOFT_DELETE,
        s422="test_admin_products::test_update_variant_rules",
    ),
    ("POST", "/admin/products/{product_id}/media"): _products(
        s400="test_admin_products::test_upload_media_errors_keep_no_file",
        s404="test_admin_products::test_upload_media_errors_keep_no_file",
        s409="n/a: concurrent first uploads still leave one main image (tested)",
        s422="test_admin_products::test_upload_media_errors_keep_no_file",
    ),
    ("PATCH", "/admin/products/{product_id}/media/{media_id}"): _products(
        s400="test_admin_products::test_update_media",
        s404="test_admin_products::test_update_media",
        s409="n/a: only a lost race on the main image; writes hold the product lock",
        s422="test_admin_products::test_update_media",
    ),
    ("DELETE", "/admin/products/{product_id}/media/{media_id}"): _products(
        s400=MALFORMED_ID,
        s404="test_admin_products::test_delete_media",
        s409="n/a: writes hold the product lock (ADR-030)",
        s422="test_admin_products::test_delete_media",
    ),
    ("POST", "/admin/media"): {
        400: "test_media_api::test_invalid_uploads_are_400",
        401: "test_media_api::test_upload_needs_authentication_before_reading_the_body",
        403: "test_media_api::test_upload_is_forbidden_without_catalog_permissions",
        404: "n/a: a standalone upload refers to nothing",
        409: "n/a: every upload gets a new server-made key",
        422: NO_RULE,
    },
}


@cache
def _tests_of(module: str) -> frozenset[str]:
    tree = ast.parse((Path(__file__).parent / f"{module}.py").read_text(encoding="utf-8"))
    return frozenset(
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name.startswith("test_")
    )


def test_coverage_map_matches_the_catalog_routes(client: AsyncClient) -> None:
    app = client._transport.app  # type: ignore[attr-defined]
    routes = {
        (method.upper(), path.removeprefix(API))
        for path, operations in app.openapi()["paths"].items()
        if path.startswith(CATALOG_PREFIXES)
        for method in operations
    }

    assert routes == set(COVERAGE)


@pytest.mark.parametrize("endpoint", sorted(COVERAGE), ids=" ".join)
def test_every_status_is_tested_or_explained(endpoint: tuple[str, str]) -> None:
    cells = COVERAGE[endpoint]

    assert sorted(cells) == list(STATUSES)
    for status, cell in cells.items():
        if cell.startswith("n/a: "):
            continue
        module, _, test = cell.partition("::")
        assert test in _tests_of(module), f"{endpoint} {status}: {cell} does not exist"


# --- gaps ----------------------------------------------------------------------------


@pytest.mark.integration
async def test_public_reads_reject_unknown_query_parameters(
    auth_client: AsyncClient, catalog: Catalog
) -> None:
    category = await catalog.category()

    response = await auth_client.get(f"{API}/categories/{category.slug}", params={"x": "1"})

    assert response.status_code == 400
    assert response.json()["error"]["details"][0]["field"] == "query.x"


@pytest.mark.integration
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("DELETE", "/admin/categories/{id}"),
        ("PATCH", "/admin/categories/{id}"),
        ("PATCH", "/admin/categories/{id}/filters"),
        ("GET", "/admin/products/{id}"),
        ("PATCH", "/admin/products/{id}"),
        ("PATCH", "/admin/products/{id}/status"),
        ("DELETE", "/admin/products/{id}"),
        ("POST", "/admin/products/{id}/variants"),
        ("PATCH", "/admin/product-variants/{id}"),
        ("DELETE", "/admin/product-variants/{id}"),
        ("PATCH", "/admin/products/{uuid}/media/{id}"),
        ("DELETE", "/admin/products/{uuid}/media/{id}"),
        ("DELETE", "/admin/products/{id}/media/{uuid}"),
    ],
)
async def test_malformed_ids_are_400(
    auth_client: AsyncClient, make_account: MakeAccount, method: str, path: str
) -> None:
    """A path id that is not a UUID is a 400 before any lookup (never a 404 or 500)."""
    actor = await make_account("super_admin")
    url = API + path.format(id="not-a-uuid", uuid=uuid4())
    body = None if method == "DELETE" else {"title": "x"}

    response = await auth_client.request(method, url, json=body, headers=actor.headers)

    assert response.status_code == 400, response.text
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert any(detail["field"].startswith("path.") for detail in error["details"])


# --- end to end ----------------------------------------------------------------------


def _png() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (40, 30), (200, 160, 40)).save(output, "PNG")
    return output.getvalue()


def _ok(response: Response, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


@pytest.mark.integration
async def test_catalog_end_to_end(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog
) -> None:
    """Admin builds and publishes a product; the public catalog shows it; archiving hides it."""
    admin = await make_account("super_admin")
    headers = admin.headers
    slug = f"cat-{uuid4().hex[:12]}"

    category = _ok(
        await auth_client.post(
            f"{API}/admin/categories", json={"title": "Rings", "slug": slug}, headers=headers
        ),
        201,
    )
    catalog.categories.append(UUID(category["id"]))  # teardown removes everything under it
    _ok(
        await auth_client.patch(
            f"{API}/admin/categories/{category['id']}/filters",
            json={
                "filters": [
                    {
                        "attribute_key": "color",
                        "label": "Color",
                        "filter_type": "color",
                        "display_order": 0,
                    },
                    {
                        "attribute_key": "price",
                        "label": "Price",
                        "filter_type": "range",
                        "display_order": 1,
                    },
                ]
            },
            headers=headers,
        )
    )
    product = _ok(
        await auth_client.post(
            f"{API}/admin/products",
            json={
                "category_id": category["id"],
                "title": "Gold ring",
                "slug": f"prd-{uuid4().hex[:12]}",
                "attributes": [{"key": "material", "value": "gold"}],
            },
            headers=headers,
        ),
        201,
    )
    products = f"{API}/admin/products/{product['id']}"
    gold = _ok(
        await auth_client.post(
            f"{products}/variants",
            json={
                "sku": f"G-{uuid4().hex[:8]}",
                "options": {"color": "gold"},
                "base_price": 250_000,
                "is_active": True,
            },
            headers=headers,
        ),
        201,
    )
    _ok(
        await auth_client.post(
            f"{products}/variants",
            json={
                "sku": f"S-{uuid4().hex[:8]}",
                "options": {"color": "silver"},
                "base_price": 180_000,
                "is_active": True,
            },
            headers=headers,
        ),
        201,
    )
    _ok(
        await auth_client.post(
            f"{products}/media",
            files={"file": ("ring.png", _png(), "image/png")},
            headers=headers,
        ),
        201,
    )
    # Stock has no admin endpoint yet (INV-02): only the gold variant gets some.
    async with AsyncSession(catalog.engine) as session, session.begin():
        session.add(
            InventoryItem(
                warehouse_id=DEFAULT_WAREHOUSE_ID,
                product_id=UUID(product["id"]),
                variant_id=UUID(gold["id"]),
                total_quantity=4,
                reserved_quantity=0,
                low_stock_threshold=0,
            )
        )

    listing = f"{API}/categories/{slug}/products"
    assert _ok(await auth_client.get(listing))["total"] == 0  # still a draft
    _ok(
        await auth_client.patch(f"{products}/status", json={"status": "published"}, headers=headers)
    )

    public_category = _ok(await auth_client.get(f"{API}/categories/{slug}"))
    assert public_category["id"] == category["id"]
    filters = _ok(await auth_client.get(f"{API}/categories/{slug}/filters"))["items"]
    assert [item["key"] for item in filters] == ["color", "price"]
    assert (filters[1]["min"], filters[1]["max"]) == (180_000, 180_000)

    [card] = _ok(await auth_client.get(listing))["items"]
    assert card["id"] == product["id"]
    assert card["price"]["final_price"] == 180_000
    assert card["price_range"] == {"min": 180_000, "max": 250_000}
    assert card["availability"] == "in_stock"
    assert card["quick_add_variant_id"] is None
    assert card["image_url"] is not None
    gold_in_stock = await auth_client.get(listing, params={"colors": "gold", "in_stock": "true"})
    assert [item["id"] for item in _ok(gold_in_stock)["items"]] == [product["id"]]
    too_cheap = await auth_client.get(listing, params={"max_price": 100_000})
    assert _ok(too_cheap)["total"] == 0

    detail = _ok(await auth_client.get(f"{API}/products/{product['slug']}"))
    assert detail["default_variant_id"] == gold["id"]  # the only purchasable variant
    assert [item["slug"] for item in detail["breadcrumb"]] == [slug]

    _ok(await auth_client.patch(f"{products}/status", json={"status": "archived"}, headers=headers))
    assert _ok(await auth_client.get(listing))["total"] == 0
    assert (await auth_client.get(f"{API}/products/{product['slug']}")).status_code == 404
