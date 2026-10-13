"""GET /cart: the cart priced by the server, with price and stock change flags (CART-03).

Read only and lock free. Amounts come from the pure calculator (ADR-031); lines go to it
sorted by line id, so one cart always gets one split. The price flag compares each line's
current final unit price with its stored baseline (ADR-041); it is UX only.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now
from app.db.models import CartItem, Product, ProductVariant, VariantOption
from app.modules.cart.repository import CartRepository
from app.modules.cart.schemas import CartLineResponse, CartResponse, LinePrice
from app.modules.cart.service import CartOwner, is_sellable
from app.modules.cart.tokens import hash_cart_token
from app.modules.catalog.product_repository import ProductRepository
from app.modules.inventory.stock import StockLevel, free_quantity
from app.modules.pricing.calculator import (
    CURRENCY,
    LineInput,
    OrderPricing,
    PricingPolicy,
    price_order,
)
from app.modules.pricing.repository import PricingSettingsRepository
from app.modules.pricing.variants import variant_price


def price_cart_lines(
    lines: Sequence[LineInput], policy: PricingPolicy, at: datetime
) -> OrderPricing:
    """Price lines in their stable order, by line id, whatever order they come in."""
    ordered = sorted(lines, key=lambda line: str(line.key))
    return price_order(ordered, policy, at=at)


@dataclass(frozen=True, slots=True)
class _Row:
    item: CartItem
    variant: ProductVariant
    product: Product


def _stock_status(quantity: int, level: StockLevel | None) -> str:
    free = free_quantity(level)
    if free == 0:
        return "out_of_stock"
    return "insufficient" if quantity > free else "ok"


class CartView:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._carts = CartRepository(session)
        self._products = ProductRepository(session)

    async def view(self, owner: CartOwner, now: datetime | None = None) -> CartResponse:
        now = now or utc_now()
        async with self._session.begin():
            cart_id = await self._cart_id(owner, now)
            rows = [] if cart_id is None else await self._rows(cart_id)
            return await self._render(rows, now)

    async def _cart_id(self, owner: CartOwner, now: datetime) -> UUID | None:
        if owner.user_id is not None:
            cart = await self._carts.find_user_cart(owner.user_id)
        elif owner.guest_token is not None:
            cart = await self._carts.find_guest_cart(hash_cart_token(owner.guest_token), now)
        else:
            cart = None
        return None if cart is None else cart.id

    async def _rows(self, cart_id: UUID) -> list[_Row]:
        statement = (
            select(CartItem, ProductVariant, Product)
            .join(ProductVariant, ProductVariant.id == CartItem.variant_id)
            .join(Product, Product.id == CartItem.product_id)
            .where(CartItem.cart_id == cart_id)
            .order_by(CartItem.id)
        )
        return [_Row(*row) for row in (await self._session.execute(statement)).all()]

    async def _options(self, variant_ids: Sequence[UUID]) -> dict[UUID, dict[str, str]]:
        options: dict[UUID, dict[str, str]] = {variant_id: {} for variant_id in variant_ids}
        if variant_ids:
            statement = select(VariantOption).where(VariantOption.variant_id.in_(variant_ids))
            for option in await self._session.scalars(statement):
                options[option.variant_id][option.option_key] = option.value
        return options

    async def _render(self, rows: Sequence[_Row], now: datetime) -> CartResponse:
        variant_ids = [row.variant.id for row in rows]
        levels = await self._products.stock_levels_of(variant_ids, now)
        options = await self._options(variant_ids)
        sellable = [row for row in rows if is_sellable(row.variant, row.product)]
        # An empty (or all-unavailable) cart prices to zeros without the settings row.
        policy = PricingPolicy()
        if sellable:
            loaded = await PricingSettingsRepository(self._session).policy()
            if loaded is None:
                # Seeded by migration 0011: a missing row is a misconfiguration (500).
                raise RuntimeError("pricing_settings row is missing")
            policy = loaded
        pricing = price_cart_lines(
            [
                LineInput(
                    key=row.item.id, price=variant_price(row.variant), quantity=row.item.quantity
                )
                for row in sellable
            ],
            policy,
            now,
        )
        priced = {line.key: line for line in pricing.lines}
        lines = []
        for row in rows:
            item = row.item
            line = priced.get(item.id)
            fields: dict[str, Any] = {}
            if line is not None:
                fields = {
                    "unit_price": LinePrice(original=line.unit.original, final=line.unit.final),
                    "subtotal": line.subtotal,
                    "product_discount": line.product_discount,
                    "code_discount": line.code_discount,
                    "tax": line.tax,
                    "total": line.total,
                }
            # Only a line that can be bought shows a price change.
            changed = line is not None and line.unit.final != item.seen_unit_price
            lines.append(
                CartLineResponse(
                    id=item.id,
                    variant_id=item.variant_id,
                    product_id=item.product_id,
                    product_title=row.product.title,
                    product_slug=row.product.slug,
                    sku=row.variant.sku,
                    options=options[item.variant_id],
                    quantity=item.quantity,
                    available=line is not None,
                    stock_status=(
                        _stock_status(item.quantity, levels[item.variant_id])
                        if line is not None
                        else None
                    ),
                    price_changed=changed,
                    previous_unit_price=item.seen_unit_price if changed else None,
                    **fields,
                )
            )
        return CartResponse(
            items=lines,
            subtotal=pricing.subtotal,
            product_discount_total=pricing.product_discount_total,
            discount_code_amount=pricing.discount_code_amount,
            tax_amount=pricing.tax_amount,
            shipping_amount=pricing.shipping_amount,
            grand_total=pricing.grand_total,
            currency=CURRENCY,
            calculated_at=pricing.calculated_at,
            has_changes=any(
                line.price_changed or not line.available or line.stock_status != "ok"
                for line in lines
            ),
        )
