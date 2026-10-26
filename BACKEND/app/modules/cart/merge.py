"""Guest cart → user cart at login (CART-04, D30, ADR-040).

Runs in its own transaction after the login is committed, so a cart problem never blocks
a login. Lock order: the user's cart, then the guest cart (ADR-040). The merge is
deterministic (guest lines by id) and idempotent: a guest cart is merged once and is then
``merged``, which no later lookup finds.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now
from app.db.models import CartItem, CartStatus, Product, ProductVariant
from app.db.models.cart import MAX_CART_LINES
from app.modules.cart.repository import CartRepository
from app.modules.cart.service import is_sellable, rebase
from app.modules.cart.tokens import hash_cart_token
from app.modules.catalog.product_repository import ProductRepository
from app.modules.inventory.stock import free_quantity

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MergeResult:
    # False when the token had no live guest cart (unknown, expired or already merged).
    merged: bool
    moved: int = 0
    combined: int = 0
    # Unavailable variants, no free stock or no room left in the user's cart.
    dropped: int = 0


class CartMerger:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._carts = CartRepository(session)
        self._products = ProductRepository(session)

    async def merge(
        self, user_id: UUID, guest_token: str, now: datetime | None = None
    ) -> MergeResult:
        now = now or utc_now()
        async with self._session.begin():
            user_cart = await self._carts.lock_user_cart(user_id)
            guest_cart = await self._carts.find_guest_cart(
                hash_cart_token(guest_token), now, lock=True
            )
            if guest_cart is None:
                return MergeResult(merged=False)
            guest_lines = await self._carts.items(guest_cart.id)
            existing = {line.variant_id: line for line in await self._carts.items(user_cart.id)}
            variant_ids = [line.variant_id for line in guest_lines]
            rows = await self._session.execute(
                select(ProductVariant, Product)
                .join(Product, Product.id == ProductVariant.product_id)
                .where(ProductVariant.id.in_(variant_ids))
            )
            sellable = {
                variant.id: variant for variant, product in rows if is_sellable(variant, product)
            }
            levels = await self._products.stock_levels_of(variant_ids, now)
            moved = combined = dropped = 0
            for guest_line in guest_lines:
                variant = sellable.get(guest_line.variant_id)
                free = free_quantity(levels[guest_line.variant_id])
                target = existing.get(guest_line.variant_id)
                if variant is None or free == 0:
                    dropped += 1
                    continue
                if target is not None:
                    # Sum, capped at free stock; never lower what the user already had.
                    wanted = min(target.quantity + guest_line.quantity, free)
                    if wanted > target.quantity:
                        target.quantity = wanted
                        rebase(target, variant, now)  # a write to the line (ADR-041)
                    combined += 1
                    continue
                if len(existing) >= MAX_CART_LINES:
                    dropped += 1
                    continue
                line = CartItem(
                    cart_id=user_cart.id,
                    product_id=guest_line.product_id,
                    variant_id=guest_line.variant_id,
                    quantity=min(guest_line.quantity, free),
                    # The shopper's own line moves with the price they last saw.
                    seen_unit_price=guest_line.seen_unit_price,
                    seen_price_version=guest_line.seen_price_version,
                )
                self._session.add(line)
                existing[line.variant_id] = line
                moved += 1
            # The guest's code comes along only when the user has none (ADR-043).
            if user_cart.discount_code_id is None and guest_cart.discount_code_id is not None:
                user_cart.discount_code_id = guest_cart.discount_code_id
            guest_cart.status = CartStatus.MERGED
            user_cart.updated_at = now
            cart_id = user_cart.id  # read before commit expires the instance
            await self._session.flush()
        result = MergeResult(merged=True, moved=moved, combined=combined, dropped=dropped)
        logger.info(
            "cart.merged",
            extra={
                "cart_id": str(cart_id),
                "moved": moved,
                "combined": combined,
                "dropped": dropped,
            },
        )
        return result
