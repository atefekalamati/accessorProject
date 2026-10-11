from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from conftest import INTERNAL_FIELDS, Catalog, count_queries, nested_keys
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.time import utc_now
from app.db.models import InventoryItem, Product, ProductStatus, ProductVariant, Warehouse
from app.db.models.inventory import WarehouseStatus

pytestmark = pytest.mark.integration

PRODUCTS = "/api/v1/products"


def _url(product_id: object) -> str:
    return f"{PRODUCTS}/{product_id}/availability"


@pytest_asyncio.fixture
async def inactive_warehouse(db_engine: AsyncEngine) -> AsyncIterator[UUID]:
    warehouse = Warehouse(name="Closed", status=WarehouseStatus.INACTIVE, is_default=False)
    async with AsyncSession(db_engine, expire_on_commit=False) as session, session.begin():
        session.add(warehouse)
    yield warehouse.id
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            delete(InventoryItem).where(InventoryItem.warehouse_id == warehouse.id)
        )
        await session.execute(delete(Warehouse).where(Warehouse.id == warehouse.id))


async def test_availability_contract_and_rules(auth_client: AsyncClient, catalog: Catalog) -> None:
    product = await catalog.product()
    in_stock = await catalog.variant(product, stock=(10, 2, 3), display_order=0)
    low = await catalog.variant(product, stock=(5, 3, 2), display_order=1)
    reserved = await catalog.variant(product, stock=(4, 4, 0), display_order=2)
    no_item = await catalog.variant(product, display_order=3)
    blocked = await catalog.variant(product, stock=(9, 0, 0), is_purchasable=False, display_order=4)

    response = await auth_client.get(_url(product.id))

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert set(body) == {"product_id", "availability", "variants"}
    assert not nested_keys(body) & (INTERNAL_FIELDS | {"max_purchasable", "quantity"})
    assert body["product_id"] == str(product.id)
    assert body["availability"] == "in_stock"
    assert body["variants"] == [
        {"variant_id": str(in_stock.id), "sku": in_stock.sku, "availability": "in_stock",
         "purchasable": True},
        {"variant_id": str(low.id), "sku": low.sku, "availability": "low_stock",
         "purchasable": True},
        {"variant_id": str(reserved.id), "sku": reserved.sku, "availability": "out_of_stock",
         "purchasable": False},
        {"variant_id": str(no_item.id), "sku": no_item.sku, "availability": "out_of_stock",
         "purchasable": False},
        {"variant_id": str(blocked.id), "sku": blocked.sku, "availability": "in_stock",
         "purchasable": False},
    ]  # fmt: skip


async def test_availability_matches_the_product_detail(
    auth_client: AsyncClient, catalog: Catalog
) -> None:
    product = await catalog.product()
    await catalog.variant(product, stock=(3, 3, 0), display_order=0)
    await catalog.variant(product, stock=(2, 0, 2), display_order=1)

    availability = (await auth_client.get(_url(product.id))).json()
    detail = (await auth_client.get(f"{PRODUCTS}/{product.slug}")).json()

    assert availability["availability"] == detail["availability"] == "low_stock"
    assert [
        (item["variant_id"], item["availability"], item["purchasable"])
        for item in availability["variants"]
    ] == [(item["id"], item["availability"], item["purchasable"]) for item in detail["variants"]]


async def test_inactive_warehouses_do_not_count(
    auth_client: AsyncClient, catalog: Catalog, inactive_warehouse: UUID
) -> None:
    product = await catalog.product()
    # Active warehouse: 2 free with threshold 2 → low stock; the closed one adds 50.
    variant = await catalog.variant(product, stock=(2, 0, 2))
    async with AsyncSession(catalog.engine) as session, session.begin():
        session.add(
            InventoryItem(
                warehouse_id=inactive_warehouse,
                product_id=product.id,
                variant_id=variant.id,
                total_quantity=50,
                reserved_quantity=0,
                low_stock_threshold=0,
            )
        )

    body = (await auth_client.get(_url(product.id))).json()

    assert body["availability"] == "low_stock"
    assert body["variants"][0]["availability"] == "low_stock"


async def test_one_variant_and_sold_out_product(auth_client: AsyncClient, catalog: Catalog) -> None:
    product = await catalog.product()
    await catalog.variant(product, stock=(1, 0, 0))
    sold_out = await catalog.variant(product, stock=(1, 1, 0))

    response = await auth_client.get(_url(product.id), params={"variant_id": str(sold_out.id)})

    assert response.status_code == 200
    body = response.json()
    assert [item["variant_id"] for item in body["variants"]] == [str(sold_out.id)]
    assert body["availability"] == "out_of_stock"
    no_variants = await catalog.product()
    await catalog.variant(no_variants, is_active=False)
    empty = (await auth_client.get(_url(no_variants.id))).json()
    assert (empty["availability"], empty["variants"]) == ("out_of_stock", [])


async def test_hidden_products_and_variants_are_404(
    auth_client: AsyncClient, catalog: Catalog
) -> None:
    shown = await catalog.product()
    await catalog.variant(shown, stock=(1, 0, 0))
    inactive = await catalog.variant(shown, stock=(1, 0, 0), is_active=False)
    deleted = await catalog.variant(shown, stock=(1, 0, 0))
    await catalog.set(ProductVariant, deleted.id, deleted_at=utc_now())
    foreign = await catalog.variant(await catalog.product())
    draft = await catalog.product(status=ProductStatus.DRAFT)
    gone = await catalog.product()
    await catalog.set(Product, gone.id, deleted_at=utc_now())

    for product_id in (draft.id, gone.id, uuid4()):
        response = await auth_client.get(_url(product_id))
        assert response.status_code == 404
        assert response.json()["error"]["message"] == "Product not found"
    for variant in (inactive, deleted, foreign):
        response = await auth_client.get(_url(shown.id), params={"variant_id": str(variant.id)})
        assert response.status_code == 404
        error = response.json()["error"]
        assert (error["code"], error["message"]) == ("NOT_FOUND", "Variant not found")
    assert len((await auth_client.get(_url(shown.id))).json()["variants"]) == 1


@pytest.mark.parametrize(
    ("product_id", "params"),
    [("not-a-uuid", {}), (None, {"variant_id": "nope"}), (None, {"warehouse_id": "x"})],
)
async def test_invalid_request_is_400(
    auth_client: AsyncClient, product_id: str | None, params: dict[str, str]
) -> None:
    response = await auth_client.get(_url(product_id or uuid4()), params=params)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_query_count_does_not_grow_with_variants(
    auth_client: AsyncClient, catalog: Catalog
) -> None:
    small = await catalog.product()
    await catalog.variant(small, stock=(1, 0, 0))
    large = await catalog.product()
    for _ in range(4):
        await catalog.variant(large, stock=(1, 0, 0))
    await auth_client.get(_url(small.id))  # warm-up (connection setup)

    with count_queries(auth_client) as small_queries:
        assert (await auth_client.get(_url(small.id))).status_code == 200
    with count_queries(auth_client) as large_queries:
        assert (await auth_client.get(_url(large.id))).status_code == 200

    assert len(large_queries) == len(small_queries)
