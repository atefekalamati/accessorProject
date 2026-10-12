"""Consolidated pricing suite: rule map, pure-function gaps and tamper tests (PRC-06).

``RULES`` maps every pricing rule (``<ADR>.<rule>``) to the test that enforces it
(``module::test``). A guard checks that each named test exists, so a renamed or deleted
test fails here. Rules already covered by their endpoint suites are only mapped; the gaps
are tested in this file.
"""

from __future__ import annotations

import ast
import random
from dataclasses import fields, replace
from datetime import timedelta
from functools import cache
from pathlib import Path
from typing import Any, Final

import pytest
from conftest import Catalog, MakeAccount
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from test_pricing_calculator import NOW, _line, _random_cart

from app.core.time import utc_now
from app.db.models import PriceHistory, ProductVariant
from app.modules.pricing.calculator import (
    CodeDiscount,
    LinePricing,
    OrderPricing,
    PricingPolicy,
    price_order,
)
from app.shared.money import RoundingMode

API = "/api/v1"
CALC = "test_pricing_calculator"
SELF = "test_pricing_security"

RULES: Final[dict[str, str]] = {
    # ADR-001 / ADR-014: money is int Toman, never float or bool.
    "ADR-014.int-inputs": f"{CALC}::test_price_order_rejects_invalid_input",
    "ADR-014.int-unit-prices": f"{CALC}::test_unit_price_rejects_invalid_prices",
    "ADR-014.int-outputs": f"{SELF}::test_every_output_amount_is_a_plain_int",
    "ADR-014.bigint-cap": f"{CALC}::test_amounts_beyond_bigint_are_rejected",
    "ADR-014.policy-types": f"{CALC}::test_policy_is_type_checked",
    # ADR-027: sale window, fingerprint.
    "ADR-027.half-open-sale-window": f"{CALC}::test_sale_window_is_half_open",
    "ADR-027.fingerprint-versions": f"{CALC}::test_fingerprint_tracks_price_and_settings_versions",
    "ADR-027.fingerprint-sale-end": f"{CALC}::test_fingerprint_changes_when_a_sale_window_ends",
    # ADR-031: tax base, single rounding, split, order.
    "ADR-031.tax-after-discounts": f"{CALC}::test_tax_after_discounts_on_taxable_lines_only",
    "ADR-031.tax-rounded-once": f"{CALC}::test_tax_is_rounded_once",
    "ADR-031.percent-code-rounded-fixed-not": (
        f"{CALC}::test_fixed_code_is_not_rounded_but_percent_code_is"
    ),
    "ADR-031.code-cap-after-rounding": f"{CALC}::test_rounding_up_never_passes_the_code_cap",
    "ADR-031.unit-and-shipping-never-rounded": (
        f"{SELF}::test_unit_prices_and_shipping_are_never_rounded"
    ),
    "ADR-031.invariants": f"{CALC}::test_invariants_over_seeded_random_carts",
    "ADR-031.largest-remainder": f"{CALC}::test_allocate_properties_over_seeded_random_inputs",
    "ADR-031.stable-order": f"{SELF}::test_line_order_never_changes_the_totals",
    # ADR-033: public pricing is server-computed; settings.
    "ADR-033.pricing-contract": "test_product_pricing::test_pricing_contract",
    "ADR-033.pricing-equals-detail": (
        "test_product_pricing::test_pricing_matches_the_product_detail"
    ),
    "ADR-033.pricing-equals-list": f"{SELF}::test_listing_price_equals_the_pricing_endpoint",
    # Unknown query parameters (amounts included) are 400; nothing is read from them.
    "ADR-033.client-price-query-rejected": f"{SELF}::test_client_amounts_in_the_query_are_400",
    "ADR-033.settings-system-fields-ignored": (
        "test_pricing_settings::test_update_bumps_version_and_audits"
    ),
    "ADR-033.settings-strict-types": "test_pricing_settings::test_invalid_body_is_400",
    "ADR-033.settings-super-admin-only": (
        "test_pricing_settings::test_only_super_admin_reads_or_changes_settings"
    ),
    # ADR-030 / ADR-035: prices change only through the pricing endpoints.
    # Sends base_price/sale_price; price_version is covered by ADR-035.price-system-fields.
    "ADR-030.variant-patch-ignores-prices": "test_admin_products::test_update_variant",
    "ADR-030.variant-price-body-validation": "test_admin_products::test_create_variant_validation",
    "ADR-030.initial-price-needs-pricing-update": (
        "test_admin_products::test_initial_price_needs_pricing_update"
    ),
    "ADR-035.price-system-fields-ignored": (
        "test_price_changes::test_price_change_writes_history_audit_and_version"
    ),
    "ADR-035.price-strict-types": "test_price_changes::test_invalid_body_is_400",
    "ADR-035.computed-amounts-rejected": f"{SELF}::test_computed_amounts_in_a_price_change_are_400",
    "ADR-035.needs-pricing-update": (
        "test_price_changes::test_price_endpoints_need_pricing_update_before_validation"
    ),
    "ADR-035.concurrent-changes": (
        "test_price_changes::test_concurrent_price_changes_chain_in_history"
    ),
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


@pytest.mark.parametrize("rule", sorted(RULES))
def test_every_rule_names_an_existing_test(rule: str) -> None:
    module, _, test = RULES[rule].partition("::")
    assert test in _tests_of(module), f"{rule}: {RULES[rule]} does not exist"


# --- pure function gaps --------------------------------------------------------------


def _amounts(result: OrderPricing) -> list[Any]:
    values: list[Any] = [
        getattr(result, field.name)
        for field in fields(result)
        if field.name not in ("lines", "currency", "calculated_at", "fingerprint", "code_applied")
    ]
    for line in result.lines:
        values += [
            getattr(line, field.name)
            for field in fields(LinePricing)
            if field.name not in ("key", "unit")
        ]
        values += [line.unit.original, line.unit.final, line.unit.discount_amount]
    return values


def test_every_output_amount_is_a_plain_int() -> None:
    """ADR-014.int-outputs: no float, Fraction or bool ever leaves the calculator."""
    rng = random.Random(20261012)
    for _ in range(200):
        cart = _random_cart(rng)
        result = price_order(
            cart["lines"], cart["policy"], at=NOW, code=cart["code"], shipping=cart["shipping"]
        )
        assert all(type(value) is int for value in _amounts(result)), cart


def test_line_order_never_changes_the_totals() -> None:
    """ADR-031.stable-order: shuffled input → same totals, components and fingerprint.

    Per-line splits may follow the caller's order on ties; callers pass lines sorted by
    line id (ADR-031), which CART-03/ORD-03 test end to end.
    """
    rng = random.Random(31)
    for _ in range(100):
        cart = _random_cart(rng)
        lines = list(cart["lines"])
        shuffled = rng.sample(lines, len(lines))
        kwargs = {"code": cart["code"], "shipping": cart["shipping"]}
        base = price_order(lines, cart["policy"], at=NOW, **kwargs)
        other = price_order(shuffled, cart["policy"], at=NOW, **kwargs)

        assert replace(other, lines=()) == replace(base, lines=())
        assert {line.key: line.unit for line in other.lines} == {
            line.key: line.unit for line in base.lines
        }


@pytest.mark.parametrize("mode", list(RoundingMode))
def test_unit_prices_and_shipping_are_never_rounded(mode: RoundingMode) -> None:
    """ADR-031.unit-and-shipping-never-rounded: only computed parts follow the step."""
    policy = PricingPolicy(
        tax_enabled=True, tax_rate_bps=900, rounding_mode=mode, rounding_step=1_000
    )
    lines = [_line("a", 12_345, 2, sale_price=11_111, tax_enabled=True), _line("b", 999)]

    result = price_order(
        lines, policy, at=NOW, code=CodeDiscount(fixed_amount=1_234), shipping=4_321
    )

    assert [(line.unit.original, line.unit.final) for line in result.lines] == [
        (12_345, 11_111),
        (999, 999),
    ]
    assert result.subtotal == 2 * 12_345 + 999
    assert result.product_discount_total == 2 * (12_345 - 11_111)
    assert result.discount_code_amount == 1_234
    assert result.shipping_amount == 4_321
    assert result.tax_amount % 1_000 == 0
    # The grand total is a sum of components; it need not be a multiple of the step.
    assert result.grand_total % 1_000 != 0


# --- tamper (integration) ------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.parametrize(
    "params",
    [{"price": "1"}, {"unit_price": "1"}, {"final_price": "1"}, {"tax": "0"}, {"total": "1"}],
)
async def test_client_amounts_in_the_query_are_400(
    auth_client: AsyncClient, catalog: Catalog, params: dict[str, str]
) -> None:
    """ADR-033.client-price-query-rejected: no client amount reaches the pricing."""
    product = await catalog.product()
    await catalog.variant(product, base_price=5_000)

    response = await auth_client.get(f"{API}/products/{product.id}/pricing", params=params)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.integration
async def test_listing_price_equals_the_pricing_endpoint(
    auth_client: AsyncClient, catalog: Catalog
) -> None:
    """ADR-033.pricing-equals-list: one source of truth for every public price."""
    category = await catalog.category()
    product = await catalog.product(category=category.id)
    now = utc_now()
    await catalog.variant(product, base_price=900, sale_price=700, sale_start_at=now - timedelta(1))
    await catalog.variant(product, base_price=650)

    pricing = (await auth_client.get(f"{API}/products/{product.id}/pricing")).json()
    listing = (await auth_client.get(f"{API}/categories/{category.slug}/products")).json()

    [card] = [item for item in listing["items"] if item["id"] == str(product.id)]
    finals = [item["price"]["final_price"] for item in pricing["variants"]]
    assert card["price"]["final_price"] == min(finals) == 650
    assert card["price_range"] == pricing["price_range"]


@pytest.mark.integration
@pytest.mark.parametrize(
    "computed",
    [{"unit_price": 1}, {"final_price": 1}, {"grand_total": 1}, {"discount_amount": 1}],
)
async def test_computed_amounts_in_a_price_change_are_400(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    catalog: Catalog,
    db_engine: AsyncEngine,
    computed: dict[str, int],
) -> None:
    """ADR-035.computed-amounts-rejected: a client cannot send a computed price."""
    admin = await make_account("admin")
    variant = await catalog.variant(await catalog.product(), base_price=1_000)

    response = await auth_client.patch(
        f"{API}/admin/product-variants/{variant.id}/price",
        json={"base_price": 2_000, **computed},
        headers=admin.headers,
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    async with AsyncSession(db_engine) as session:
        stored = await session.get(ProductVariant, variant.id)
        history = await session.scalars(
            select(PriceHistory.id).where(PriceHistory.variant_id == variant.id)
        )
        assert stored is not None
        assert (stored.base_price, stored.price_version) == (1_000, 0)
        assert list(history) == []


def test_rule_map_covers_this_module() -> None:
    """Every test in this module (except the guards) is named by a rule."""
    named = {
        target.partition("::")[2] for target in RULES.values() if target.startswith(f"{SELF}::")
    }
    guards = {"test_every_rule_names_an_existing_test", "test_rule_map_covers_this_module"}
    assert _tests_of(SELF) - guards == named
