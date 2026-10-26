from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from conftest import Catalog, MakeAccount
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.time import utc_now
from app.db.models import AuditLog, PriceHistory, Product, ProductVariant

pytestmark = pytest.mark.integration

ADMIN = "/api/v1/admin"


def _variant_url(variant_id: object) -> str:
    return f"{ADMIN}/product-variants/{variant_id}/price"


def _product_url(product_id: object) -> str:
    return f"{ADMIN}/products/{product_id}/price"


def _error(response: Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body: dict[str, Any] = response.json()["error"]
    assert body["code"] == code
    return body


async def _history(engine: AsyncEngine, variant_id: UUID) -> list[PriceHistory]:
    async with AsyncSession(engine) as session:
        statement = select(PriceHistory).where(PriceHistory.variant_id == variant_id)
        return list((await session.scalars(statement)).all())


async def _variant(engine: AsyncEngine, variant_id: UUID) -> ProductVariant:
    async with AsyncSession(engine) as session:
        statement = select(ProductVariant).where(ProductVariant.id == variant_id)
        return (await session.scalars(statement)).one()


# --- change --------------------------------------------------------------------------


async def test_price_change_writes_history_audit_and_version(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog, db_engine: AsyncEngine
) -> None:
    admin = await make_account("admin")
    product = await catalog.product()
    variant = await catalog.variant(product, base_price=1_000)
    start = utc_now() + timedelta(days=1)
    end = start + timedelta(days=7)

    response = await auth_client.patch(
        _variant_url(variant.id),
        json={
            "base_price": 1_200,
            "sale_price": 900,
            "sale_start_at": start.isoformat(),
            "sale_end_at": end.isoformat(),
            "reason": " campaign ",
            # System fields are ignored, never applied.
            "price_version": 99,
            "tax_enabled": True,
        },
        headers=admin.headers,
    )

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert (body["base_price"], body["sale_price"], body["price_version"]) == (1_200, 900, 1)
    stored = await _variant(db_engine, variant.id)
    assert (stored.price_version, stored.tax_enabled) == (1, False)
    [row] = await _history(db_engine, variant.id)
    assert (row.old_base_price, row.new_base_price) == (1_000, 1_200)
    assert (row.old_sale_price, row.new_sale_price) == (None, 900)
    assert row.new_sale_start_at == start and row.new_sale_end_at == end
    assert (row.reason, row.changed_by, row.product_id) == ("campaign", admin.id, product.id)
    async with AsyncSession(db_engine) as session:
        [audit] = (
            await session.scalars(
                select(AuditLog).where(
                    AuditLog.entity_id == variant.id,
                    AuditLog.action == "product_variant.price_changed",
                )
            )
        ).all()
    diff = audit.metadata_["diff"]
    assert (diff["base_price"]["before"], diff["base_price"]["after"]) == (1_000, 1_200)
    assert (diff["price_version"]["before"], diff["price_version"]["after"]) == (0, 1)
    assert diff["price_history_id"]["after"] == str(row.id)


async def test_unchanged_price_is_a_noop(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog, db_engine: AsyncEngine
) -> None:
    admin = await make_account("admin")
    variant = await catalog.variant(await catalog.product(), base_price=1_000)

    response = await auth_client.patch(
        _variant_url(variant.id), json={"base_price": 1_000}, headers=admin.headers
    )

    assert response.status_code == 200
    assert response.json()["price_version"] == 0
    assert await _history(db_engine, variant.id) == []
    assert (await _variant(db_engine, variant.id)).price_version == 0
    async with AsyncSession(db_engine) as session:
        audits = (
            await session.scalars(select(AuditLog).where(AuditLog.entity_id == variant.id))
        ).all()
    assert audits == []


async def test_removing_the_sale_removes_its_window(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog, db_engine: AsyncEngine
) -> None:
    admin = await make_account("admin")
    now = utc_now()
    variant = await catalog.variant(
        await catalog.product(),
        base_price=1_000,
        sale_price=800,
        sale_start_at=now - timedelta(days=1),
        sale_end_at=now + timedelta(days=1),
    )

    response = await auth_client.patch(
        _variant_url(variant.id), json={"sale_price": None}, headers=admin.headers
    )

    body = response.json()
    assert (body["sale_price"], body["sale_start_at"], body["sale_end_at"]) == (None, None, None)
    [row] = await _history(db_engine, variant.id)
    assert (row.old_sale_price, row.new_sale_price, row.new_sale_end_at) == (800, None, None)


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"reason": "only a reason"},
        {"price_version": 3},  # empty once system fields are dropped
        {"unknown": 1},
        {"base_price": None},
        {"base_price": 0},
        {"base_price": 1_000_000_000_001},
        {"base_price": 10.5},
        {"base_price": "1000"},
        {"base_price": True},
        {"base_price": 100, "sale_price": 101},
        {"sale_price": None, "sale_end_at": "2030-01-01T00:00:00Z"},
        {"sale_price": 10, "sale_start_at": "2030-01-01T00:00:00"},  # naive time
        {
            "sale_price": 10,
            "sale_start_at": "2030-01-02T00:00:00Z",
            "sale_end_at": "2030-01-01T00:00:00Z",
        },
        {"base_price": 100, "reason": "   "},
    ],
)
async def test_invalid_body_is_400(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog, body: dict[str, Any]
) -> None:
    admin = await make_account("admin")
    variant = await catalog.variant(await catalog.product(), base_price=1_000)

    response = await auth_client.patch(_variant_url(variant.id), json=body, headers=admin.headers)

    _error(response, 400, "VALIDATION_ERROR")


async def test_conflicts_with_the_stored_price_are_422(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog, db_engine: AsyncEngine
) -> None:
    admin = await make_account("admin")
    product = await catalog.product()
    on_sale = await catalog.variant(product, base_price=1_000, sale_price=800)
    plain = await catalog.variant(product, base_price=1_000)
    unpriced = await catalog.variant(product, base_price=None, is_active=False)
    later = (utc_now() + timedelta(days=3)).isoformat()

    cases = [
        (on_sale.id, {"base_price": 700}, "sale_above_base"),
        (plain.id, {"sale_end_at": later}, "window_without_sale"),
        (unpriced.id, {"sale_price": 10}, "base_price_required"),
    ]
    for variant_id, body, kind in cases:
        response = await auth_client.patch(
            _variant_url(variant_id), json=body, headers=admin.headers
        )
        assert _error(response, 422, "BUSINESS_RULE_VIOLATION")["details"][0]["type"] == kind
        assert await _history(db_engine, variant_id) == []
    # A variant created without a price gets its first one here.
    response = await auth_client.patch(
        _variant_url(unpriced.id), json={"base_price": 500}, headers=admin.headers
    )
    assert response.status_code == 200
    [row] = await _history(db_engine, unpriced.id)
    assert (row.old_base_price, row.new_base_price) == (None, 500)


async def test_missing_or_deleted_targets_are_404(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog
) -> None:
    admin = await make_account("admin")
    product = await catalog.product()
    deleted = await catalog.variant(product)
    await catalog.set(ProductVariant, deleted.id, deleted_at=utc_now())
    gone = await catalog.product()
    gone_variant = await catalog.variant(gone)
    await catalog.set(Product, gone.id, deleted_at=utc_now())

    for variant_id in (deleted.id, uuid4()):
        response = await auth_client.patch(
            _variant_url(variant_id), json={"base_price": 5}, headers=admin.headers
        )
        _error(response, 404, "NOT_FOUND")
    response = await auth_client.patch(
        _variant_url(gone_variant.id), json={"base_price": 5}, headers=admin.headers
    )
    _error(response, 404, "NOT_FOUND")
    for product_id in (gone.id, uuid4()):
        response = await auth_client.patch(
            _product_url(product_id), json={"base_price": 5}, headers=admin.headers
        )
        _error(response, 404, "NOT_FOUND")
    for url in (_variant_url("nope"), _product_url("nope")):
        response = await auth_client.patch(url, json={"base_price": 5}, headers=admin.headers)
        _error(response, 400, "VALIDATION_ERROR")


async def test_product_price_needs_exactly_one_variant(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog, db_engine: AsyncEngine
) -> None:
    admin = await make_account("admin")
    single = await catalog.product()
    only = await catalog.variant(single, base_price=1_000)
    # A deleted variant does not count.
    removed = await catalog.variant(single, base_price=2_000)
    await catalog.set(ProductVariant, removed.id, deleted_at=utc_now())
    several = await catalog.product()
    await catalog.variant(several)
    await catalog.variant(several, is_active=False)  # inactive ones count: D29

    ok = await auth_client.patch(
        _product_url(single.id), json={"base_price": 1_500}, headers=admin.headers
    )
    refused = await auth_client.patch(
        _product_url(several.id), json={"base_price": 1_500}, headers=admin.headers
    )

    assert ok.status_code == 200
    assert (ok.json()["variant_id"], ok.json()["base_price"]) == (str(only.id), 1_500)
    body = _error(refused, 422, "BUSINESS_RULE_VIOLATION")
    assert body["details"][0]["type"] == "multiple_variants"
    invalid = await auth_client.patch(
        _product_url(single.id), json={"base_price": 1.5}, headers=admin.headers
    )
    _error(invalid, 400, "VALIDATION_ERROR")
    assert len(await _history(db_engine, only.id)) == 1


# --- access --------------------------------------------------------------------------


async def test_price_endpoints_need_pricing_update_before_validation(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    target = uuid4()
    urls = [_variant_url(target), _product_url(target)]
    for url in urls:
        _error(await auth_client.patch(url, json={"base_price": "x"}), 401, "UNAUTHORIZED")
    _error(await auth_client.get(f"{ADMIN}/products/{target}/price-history"), 401, "UNAUTHORIZED")
    for role in ("content_manager", "support", "customer"):
        actor = await make_account(role)
        for url in urls:
            response = await auth_client.patch(url, json={"base_price": "x"}, headers=actor.headers)
            _error(response, 403, "FORBIDDEN")
        response = await auth_client.get(
            f"{ADMIN}/products/{target}/price-history", headers=actor.headers
        )
        _error(response, 403, "FORBIDDEN")


# --- history -------------------------------------------------------------------------


async def test_history_lists_changes_newest_first(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog
) -> None:
    admin = await make_account("admin")
    product = await catalog.product()
    created = await auth_client.post(
        f"{ADMIN}/products/{product.id}/variants",
        json={"sku": f"H-{uuid4().hex[:8]}", "base_price": 100},
        headers=admin.headers,
    )
    assert created.status_code == 201, created.text
    variant_id = created.json()["id"]
    for price in (200, 300):
        response = await auth_client.patch(
            _variant_url(variant_id), json={"base_price": price}, headers=admin.headers
        )
        assert response.status_code == 200

    page = await auth_client.get(
        f"{ADMIN}/products/{product.id}/price-history",
        params={"limit": 2},
        headers=admin.headers,
    )

    assert page.status_code == 200
    assert page.headers["cache-control"] == "no-store"
    body = page.json()
    assert (body["total"], body["pages"]) == (3, 2)
    everything = await auth_client.get(
        f"{ADMIN}/products/{product.id}/price-history", headers=admin.headers
    )
    rows = everything.json()["items"]
    # Newest first, in insertion order even within one clock tick: created with 100 (from
    # nothing), then 200, then 300.
    assert [(row["old_base_price"], row["new_base_price"]) for row in rows] == [
        (200, 300),
        (100, 200),
        (None, 100),
    ]
    assert [row["new_base_price"] for row in body["items"]] == [300, 200]
    # The history of a deleted product stays visible to admins (ADR-035).
    await catalog.set(Product, product.id, deleted_at=utc_now())
    after_delete = await auth_client.get(
        f"{ADMIN}/products/{product.id}/price-history", headers=admin.headers
    )
    assert after_delete.status_code == 200
    assert after_delete.json()["total"] == 3
    missing = await auth_client.get(
        f"{ADMIN}/products/{uuid4()}/price-history", headers=admin.headers
    )
    _error(missing, 404, "NOT_FOUND")
    bad = await auth_client.get(
        f"{ADMIN}/products/{product.id}/price-history", params={"sort": "x"}, headers=admin.headers
    )
    _error(bad, 400, "VALIDATION_ERROR")


# --- concurrency ---------------------------------------------------------------------


async def test_concurrent_price_changes_chain_in_history(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog, db_engine: AsyncEngine
) -> None:
    admin = await make_account("admin")
    variant = await catalog.variant(await catalog.product(), base_price=1_000)

    responses = await asyncio.gather(
        *(
            auth_client.patch(
                _variant_url(variant.id), json={"base_price": p}, headers=admin.headers
            )
            for p in (2_000, 3_000)
        )
    )

    assert [response.status_code for response in responses] == [200, 200]
    stored = await _variant(db_engine, variant.id)
    assert stored.price_version == 2
    rows = await _history(db_engine, variant.id)
    pairs = {(row.old_base_price, row.new_base_price) for row in rows}
    # One ran after the other: the second saw the first one's price as "old".
    assert pairs in (
        {(1_000, 2_000), (2_000, 3_000)},
        {(1_000, 3_000), (3_000, 2_000)},
    )
    # The final price is the "new" side that no other row took as its "old".
    olds = {row.old_base_price for row in rows}
    assert {row.new_base_price for row in rows} - olds == {stored.base_price}


async def test_price_change_racing_a_variant_delete(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog, db_engine: AsyncEngine
) -> None:
    admin = await make_account("admin")
    product = await catalog.product(status="draft", published_at=None)
    await catalog.variant(product, base_price=1_000)  # the product keeps a variant
    victim = await catalog.variant(product, base_price=1_000)

    price, deletion = await asyncio.gather(
        auth_client.patch(_variant_url(victim.id), json={"base_price": 7}, headers=admin.headers),
        auth_client.delete(f"{ADMIN}/product-variants/{victim.id}", headers=admin.headers),
    )

    assert deletion.status_code == 204, deletion.text
    # Either the change landed before the delete (with its history) or it found nothing.
    if price.status_code == 200:
        assert len(await _history(db_engine, victim.id)) == 1
    else:
        _error(price, 404, "NOT_FOUND")
        assert await _history(db_engine, victim.id) == []
