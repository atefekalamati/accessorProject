from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from conftest import INTERNAL_FIELDS, Catalog, nested_keys
from httpx import AsyncClient

from app.core.time import utc_now
from app.db.models import Product, ProductStatus, ProductVariant

pytestmark = pytest.mark.integration

PRODUCTS = "/api/v1/products"


def _url(product_id: object) -> str:
    return f"{PRODUCTS}/{product_id}/pricing"


async def test_pricing_contract(auth_client: AsyncClient, catalog: Catalog) -> None:
    product = await catalog.product()
    now = utc_now()
    on_sale = await catalog.variant(
        product,
        base_price=200_000,
        sale_price=150_000,
        sale_start_at=now - timedelta(days=1),
        sale_end_at=now + timedelta(days=1),
        display_order=0,
    )
    plain = await catalog.variant(product, base_price=90_000, display_order=1)

    response = await auth_client.get(_url(product.id))

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert set(body) == {
        "product_id",
        "currency",
        "tax_included",
        "calculated_at",
        "price_range",
        "variants",
    }
    assert not nested_keys(body) & INTERNAL_FIELDS
    assert body["product_id"] == str(product.id)
    assert (body["currency"], body["tax_included"]) == ("TOMAN", False)
    assert body["price_range"] == {"min": 90_000, "max": 150_000}
    assert body["variants"] == [
        {
            "variant_id": str(on_sale.id),
            "sku": on_sale.sku,
            "price": {
                "base_price": 200_000,
                "sale_price": 150_000,
                "final_price": 150_000,
                "discount_amount": 50_000,
                "discount_percent": 25,
            },
        },
        {
            "variant_id": str(plain.id),
            "sku": plain.sku,
            "price": {
                "base_price": 90_000,
                "sale_price": None,
                "final_price": 90_000,
                "discount_amount": 0,
                "discount_percent": 0,
            },
        },
    ]


async def test_pricing_matches_the_product_detail(
    auth_client: AsyncClient, catalog: Catalog
) -> None:
    product = await catalog.product()
    now = utc_now()
    await catalog.variant(
        product, base_price=500, sale_price=400, sale_start_at=now - timedelta(1), display_order=0
    )
    # A sale that ended or has not started yet has no effect.
    await catalog.variant(
        product,
        base_price=700,
        sale_price=100,
        sale_start_at=now - timedelta(days=2),
        sale_end_at=now - timedelta(days=1),
        display_order=1,
    )
    await catalog.variant(
        product, base_price=800, sale_price=100, sale_start_at=now + timedelta(1), display_order=2
    )

    pricing = (await auth_client.get(_url(product.id))).json()
    detail = (await auth_client.get(f"{PRODUCTS}/{product.slug}")).json()

    assert [item["price"] for item in pricing["variants"]] == [
        item["price"] for item in detail["variants"]
    ]
    assert [item["price"]["final_price"] for item in pricing["variants"]] == [400, 700, 800]
    assert pricing["price_range"] == detail["price_range"]


async def test_one_variant_with_variant_id(auth_client: AsyncClient, catalog: Catalog) -> None:
    product = await catalog.product()
    await catalog.variant(product, base_price=100)
    second = await catalog.variant(product, base_price=300)

    before = utc_now()
    response = await auth_client.get(_url(product.id), params={"variant_id": str(second.id)})
    after = utc_now()

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    calculated_at = datetime.fromisoformat(body["calculated_at"])
    assert calculated_at.tzinfo is not None and before <= calculated_at <= after
    assert [item["variant_id"] for item in body["variants"]] == [str(second.id)]
    assert body["price_range"] == {"min": 300, "max": 300}


async def test_product_without_public_variants(auth_client: AsyncClient, catalog: Catalog) -> None:
    product = await catalog.product()
    await catalog.variant(product, is_active=False)

    response = await auth_client.get(_url(product.id))

    assert response.status_code == 200
    assert (response.json()["variants"], response.json()["price_range"]) == ([], None)


async def test_hidden_products_and_variants_are_404(
    auth_client: AsyncClient, catalog: Catalog
) -> None:
    shown = await catalog.product()
    await catalog.variant(shown)
    inactive = await catalog.variant(shown, is_active=False)
    deleted = await catalog.variant(shown)
    await catalog.set(ProductVariant, deleted.id, deleted_at=utc_now())
    other = await catalog.product()
    foreign = await catalog.variant(other)
    draft = await catalog.product(status=ProductStatus.DRAFT)
    await catalog.variant(draft)
    archived = await catalog.product(status=ProductStatus.ARCHIVED, published_at=utc_now())
    gone = await catalog.product()
    await catalog.set(Product, gone.id, deleted_at=utc_now())

    for product_id in (draft.id, archived.id, gone.id, uuid4()):
        response = await auth_client.get(_url(product_id))
        assert response.status_code == 404
        assert response.json()["error"]["message"] == "Product not found"
    for variant in (inactive, deleted, foreign):
        response = await auth_client.get(_url(shown.id), params={"variant_id": str(variant.id)})
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"
    # Inactive and deleted variants are left out of the full answer too.
    body = (await auth_client.get(_url(shown.id))).json()
    assert len(body["variants"]) == 1


@pytest.mark.parametrize(
    ("product_id", "params"),
    [
        ("not-a-uuid", {}),
        (None, {"variant_id": "nope"}),
        (None, {"currency": "IRR"}),
    ],
)
async def test_invalid_request_is_400(
    auth_client: AsyncClient, product_id: str | None, params: dict[str, str]
) -> None:
    response = await auth_client.get(_url(product_id or uuid4()), params=params)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
