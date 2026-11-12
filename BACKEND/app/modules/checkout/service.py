"""Checkout quote: the user's cart re-checked with an address and a shipping method (ORD-03).

``build_quote`` opens no transaction and takes no lock, so ``POST /orders`` (ORD-04) runs
it inside its own transaction after its locks (a pre-locked code may be passed in, ADR-044)
and uses the returned ``Quote`` to write the order snapshot. Checks, in order (ADR-047):
cart empty 422 → address not the user's 404 → shipping method 422 → unsellable line 422
(SD rule) → free stock 409 → applied code no longer applies 422. Pricing follows ADR-045:
lines by id, the code, the free-shipping basis, the quote, then ``shipping=amount``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BusinessRuleError, ConflictError, ErrorCode, NotFoundError
from app.core.time import utc_now
from app.db.models import Address, DiscountCode, ShippingMethod, VariantOption
from app.modules.cart.repository import CartRepository
from app.modules.cart.schemas import LinePrice
from app.modules.cart.service import is_sellable
from app.modules.cart.view import (
    CartRow,
    line_inputs,
    load_policy,
    load_rows,
    price_cart_lines,
    price_with_code,
)
from app.modules.catalog.product_repository import ProductRepository
from app.modules.checkout.quote import QuotedCode, QuotedShipping, quote_fingerprint
from app.modules.checkout.schemas import (
    CheckoutQuoteResponse,
    QuoteDiscount,
    QuoteLine,
    QuoteShipping,
)
from app.modules.discounts.repository import DiscountRepository
from app.modules.discounts.rules import (
    CodeRules,
    Usage,
    discount_error,
    rules_of,
    to_code_discount,
)
from app.modules.inventory.stock import free_quantity
from app.modules.pricing.calculator import CURRENCY, LineInput, OrderPricing, PricingPolicy
from app.modules.shipping.calculator import (
    ShippingCalculator,
    ShippingContext,
    ShippingRates,
    get_shipping_calculator,
    rates_of,
    shipping_basis,
)
from app.modules.shipping.repository import ShippingRepository


@dataclass(frozen=True, slots=True)
class Quote:
    """Everything ORD-04 needs to place the order without querying again."""

    rows: tuple[CartRow, ...]
    lines: tuple[LineInput, ...]
    options: dict[UUID, dict[str, str]]
    policy: PricingPolicy
    pricing: OrderPricing
    code: DiscountCode | None
    # The rules the order was priced with: RedemptionService.redeem re-checks them.
    priced_rules: CodeRules | None
    usage: Usage | None
    method: ShippingMethod
    rates: ShippingRates
    address: Address
    fingerprint: str
    calculated_at: datetime


def _cart_empty() -> BusinessRuleError:
    return BusinessRuleError(
        message="The cart is empty", details=[{"field": "cart", "type": "cart_empty"}]
    )


def _unavailable(rows: Sequence[CartRow]) -> BusinessRuleError:
    return BusinessRuleError(
        message="Some cart items can no longer be bought",
        details=[
            {"field": "items", "item_id": str(row.item.id), "type": "line_unavailable"}
            for row in rows
        ],
    )


def _address_not_found() -> NotFoundError:
    return NotFoundError(message="Address not found")


class CheckoutService:
    def __init__(self, session: AsyncSession, calculator: ShippingCalculator | None = None) -> None:
        self._session = session
        self._calculator = calculator or get_shipping_calculator()

    async def validate(
        self,
        user_id: UUID,
        address_id: UUID,
        shipping_method_id: UUID,
        now: datetime | None = None,
    ) -> CheckoutQuoteResponse:
        async with self._session.begin():
            quote = await self.build_quote(
                user_id, address_id, shipping_method_id, now=now or utc_now()
            )
        return render(quote)

    async def build_quote(
        self,
        user_id: UUID,
        address_id: UUID,
        shipping_method_id: UUID,
        *,
        now: datetime,
        locked_code: DiscountCode | None = None,
        check_stock: bool = True,
    ) -> Quote:
        """The priced quote, or the first failing check's error (see module docstring).

        ``check_stock=False`` skips the lock-free stock read: under ORD-04 the reservation
        is the authoritative check.
        """
        cart = await CartRepository(self._session).find_user_cart(user_id)
        rows = [] if cart is None else await load_rows(self._session, cart.id)
        if not rows:
            raise _cart_empty()
        address = (
            await self._session.scalars(
                select(Address).where(Address.id == address_id, Address.user_id == user_id)
            )
        ).one_or_none()
        if address is None:
            raise _address_not_found()
        method = await ShippingRepository(self._session).get_selectable(shipping_method_id)
        unsellable = [row for row in rows if not is_sellable(row.variant, row.product)]
        if unsellable:
            raise _unavailable(unsellable)
        if check_stock:
            await self._check_stock(rows, now)

        lines = line_inputs(rows)
        policy = await load_policy(self._session, True)
        code_id = None if cart is None else cart.discount_code_id
        if locked_code is not None and locked_code.id != code_id:
            raise ValueError("locked_code must be the cart's code")
        code = locked_code
        if code is None and code_id is not None:
            code = await self._session.get(DiscountCode, code_id)
        priced_rules: CodeRules | None = None
        usage: Usage | None = None
        if code is None:
            base = price_cart_lines(lines, policy, now)
        else:
            priced_rules = rules_of(code)
            usage = await DiscountRepository(self._session).usage_for_user(code.id, user_id)
            base, rejection = price_with_code(lines, policy, now, priced_rules, usage)
            if rejection is not None:
                raise discount_error(rejection)

        rates = rates_of(method)
        amount = self._calculator.quote(
            rates,
            ShippingContext(
                basis=shipping_basis(base), province=address.province, city=address.city
            ),
        )
        pricing = price_cart_lines(
            lines,
            policy,
            now,
            None if priced_rules is None else to_code_discount(priced_rules),
            shipping=amount,
        )
        if pricing.discount_code_amount != base.discount_code_amount:
            # Shipping never feeds the code (ADR-045); a change here is a calculator bug.
            raise RuntimeError("the code amount changed when shipping was added")
        fingerprint = quote_fingerprint(
            pricing,
            None if code is None or priced_rules is None else QuotedCode(code.id, priced_rules),
            QuotedShipping(method.id, rates),
            [(str(line.key), line.quantity) for line in lines],
        )
        return Quote(
            rows=tuple(rows),
            lines=tuple(sorted(lines, key=lambda line: str(line.key))),
            options=await self._options([row.variant.id for row in rows]),
            policy=policy,
            pricing=pricing,
            code=code,
            priced_rules=priced_rules,
            usage=usage,
            method=method,
            rates=rates,
            address=address,
            fingerprint=fingerprint,
            calculated_at=now,
        )

    async def _check_stock(self, rows: Sequence[CartRow], now: datetime) -> None:
        levels = await ProductRepository(self._session).stock_levels_of(
            [row.variant.id for row in rows], now
        )
        short = [
            row.variant.id
            for row in rows
            if row.item.quantity > free_quantity(levels.get(row.variant.id))
        ]
        if short:
            raise ConflictError(
                code=ErrorCode.INSUFFICIENT_STOCK,
                message="Not enough stock",
                details=[
                    {"variant_id": str(variant_id), "type": "insufficient_stock"}
                    for variant_id in short
                ],
            )

    async def _options(self, variant_ids: Sequence[UUID]) -> dict[UUID, dict[str, str]]:
        options: dict[UUID, dict[str, str]] = {variant_id: {} for variant_id in variant_ids}
        statement = select(VariantOption).where(VariantOption.variant_id.in_(variant_ids))
        for option in await self._session.scalars(statement):
            options[option.variant_id][option.option_key] = option.value
        return options


def render(quote: Quote) -> CheckoutQuoteResponse:
    pricing = quote.pricing
    rows = {row.item.id: row for row in quote.rows}
    items = []
    for line in pricing.lines:
        row = rows[UUID(str(line.key))]
        items.append(
            QuoteLine(
                id=row.item.id,
                variant_id=row.variant.id,
                product_id=row.product.id,
                product_title=row.product.title,
                sku=row.variant.sku,
                options=quote.options[row.variant.id],
                quantity=line.quantity,
                unit_price=LinePrice(original=line.unit.original, final=line.unit.final),
                subtotal=line.subtotal,
                product_discount=line.product_discount,
                code_discount=line.code_discount,
                tax=line.tax,
                total=line.total,
            )
        )
    return CheckoutQuoteResponse(
        items=items,
        subtotal=pricing.subtotal,
        product_discount_total=pricing.product_discount_total,
        discount_code_amount=pricing.discount_code_amount,
        tax_amount=pricing.tax_amount,
        shipping_amount=pricing.shipping_amount,
        grand_total=pricing.grand_total,
        currency=CURRENCY,
        calculated_at=pricing.calculated_at,
        discount=None
        if quote.code is None
        else QuoteDiscount(code=quote.code.code, amount=pricing.discount_code_amount),
        shipping=QuoteShipping(
            method_id=quote.method.id,
            title=quote.method.title,
            cost=quote.rates.cost,
            free_shipping_threshold=quote.rates.free_shipping_threshold,
            amount=pricing.shipping_amount,
        ),
        address_id=quote.address.id,
        fingerprint=quote.fingerprint,
    )
