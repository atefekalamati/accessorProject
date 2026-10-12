"""Cart writes: add, change and remove lines against free stock (CART-02, ADR-040).

Adding to a cart reserves nothing (ADR-007): stock is only read, with the same rule as the
public availability (active warehouses, expired holds are free; ADR-029, ADR-036). Every
write locks the cart row first, so writes to one cart never interleave.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BusinessRuleError, ConflictError, ErrorCode, NotFoundError
from app.core.time import utc_now
from app.db.models import Cart, CartItem, Product, ProductStatus, ProductVariant
from app.db.models.cart import MAX_CART_LINES
from app.db.models.common import not_deleted
from app.modules.cart.repository import CartRepository
from app.modules.cart.tokens import GUEST_CART_TTL, generate_cart_token, hash_cart_token
from app.modules.catalog.product_repository import ProductRepository
from app.modules.inventory.stock import free_quantity

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CartOwner:
    """Who a cart request acts for: a signed-in user, or a guest with (maybe) a token."""

    user_id: UUID | None
    guest_token: str | None


@dataclass(frozen=True, slots=True)
class CartWrite:
    item: CartItem | None
    # Set when the guest's cookie must be (re)issued: a new cart, or a renewed expiry.
    guest_token: str | None


def _item_not_found() -> NotFoundError:
    return NotFoundError(message="Cart item not found")


def _variant_not_found() -> NotFoundError:
    return NotFoundError(message="Variant not found")


class CartService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._carts = CartRepository(session)
        self._products = ProductRepository(session)

    async def add_item(
        self, owner: CartOwner, variant_id: UUID, quantity: int, now: datetime | None = None
    ) -> CartWrite:
        now = now or utc_now()
        async with self._session.begin():
            cart, token = await self._lock_cart(owner, now, create=True)
            assert cart is not None  # create=True always returns a cart
            variant = await self._sellable_variant(variant_id)
            line = await self._carts.item_for_variant(cart.id, variant_id)
            # The cheaper, stock-independent rule first: a full cart is 422 whatever the stock.
            if line is None and await self._carts.line_count(cart.id) >= MAX_CART_LINES:
                raise BusinessRuleError(
                    message=f"A cart holds at most {MAX_CART_LINES} lines",
                    details=[{"field": "variant_id", "type": "cart_full"}],
                )
            wanted = quantity + (line.quantity if line is not None else 0)
            await self._check_stock(variant_id, wanted, now)
            if line is None:
                line = CartItem(
                    cart_id=cart.id,
                    product_id=variant.product_id,
                    variant_id=variant_id,
                    quantity=wanted,
                )
                self._session.add(line)
            else:
                line.quantity = wanted
            self._touch(cart, now)
            await self._session.flush()
        logger.info(
            "cart.item_added", extra={"cart_id": str(cart.id), "variant_id": str(variant_id)}
        )
        return CartWrite(line, token)

    async def update_item(
        self, owner: CartOwner, item_id: UUID, quantity: int, now: datetime | None = None
    ) -> CartWrite:
        """Set a line's quantity. Lowering it is always allowed; raising it needs the
        variant to be for sale and enough free stock."""
        now = now or utc_now()
        async with self._session.begin():
            cart, token = await self._lock_cart(owner, now, create=False)
            line = None if cart is None else await self._carts.item(cart.id, item_id)
            if cart is None or line is None:
                raise _item_not_found()
            if quantity > line.quantity:
                await self._sellable_variant(line.variant_id, in_cart=True)
                await self._check_stock(line.variant_id, quantity, now)
            line.quantity = quantity
            self._touch(cart, now)
            await self._session.flush()
        return CartWrite(line, token)

    async def remove_item(
        self, owner: CartOwner, item_id: UUID, now: datetime | None = None
    ) -> CartWrite:
        now = now or utc_now()
        async with self._session.begin():
            cart, token = await self._lock_cart(owner, now, create=False)
            line = None if cart is None else await self._carts.item(cart.id, item_id)
            if cart is None or line is None:
                raise _item_not_found()
            await self._session.delete(line)
            self._touch(cart, now)
            await self._session.flush()
        return CartWrite(None, token)

    async def _lock_cart(
        self, owner: CartOwner, now: datetime, *, create: bool
    ) -> tuple[Cart | None, str | None]:
        """The owner's cart under FOR UPDATE; a guest without a live cart gets a new one
        only when ``create``. Returns the guest token to (re)issue as a cookie."""
        if owner.user_id is not None:
            if create:
                return await self._carts.lock_user_cart(owner.user_id), None
            return await self._carts.find_user_cart(owner.user_id, lock=True), None
        token = owner.guest_token
        if token is not None:
            cart = await self._carts.find_guest_cart(hash_cart_token(token), now, lock=True)
            if cart is not None:
                return cart, token
        if not create:
            return None, None
        token = generate_cart_token()
        return await self._carts.create_guest_cart(hash_cart_token(token), now), token

    async def _sellable_variant(self, variant_id: UUID, *, in_cart: bool = False) -> ProductVariant:
        """A public variant (SD rule: hidden → 404) that is for sale (else 422).

        For a line already in the cart (``in_cart``) a hidden variant is 422 instead: the
        client sees the line, so "not found" would be misleading.
        """
        statement = (
            select(ProductVariant)
            .join(Product, Product.id == ProductVariant.product_id)
            .where(
                ProductVariant.id == variant_id,
                not_deleted(ProductVariant),
                ProductVariant.is_active.is_(True),
                ProductVariant.base_price.is_not(None),
                Product.status == ProductStatus.PUBLISHED,
                not_deleted(Product),
            )
        )
        variant = (await self._session.scalars(statement)).one_or_none()
        if variant is None and in_cart:
            raise BusinessRuleError(
                message="This variant is no longer available",
                details=[{"field": "quantity", "type": "variant_unavailable"}],
            )
        if variant is None:
            raise _variant_not_found()
        if not variant.is_purchasable:
            raise BusinessRuleError(
                message="This variant is not for sale",
                details=[{"field": "variant_id", "type": "not_purchasable"}],
            )
        return variant

    async def _check_stock(self, variant_id: UUID, wanted: int, now: datetime) -> None:
        levels = await self._products.stock_levels_of([variant_id], now)
        if wanted > free_quantity(levels[variant_id]):
            # No stock numbers in public errors (ADR-029).
            raise ConflictError(
                code=ErrorCode.INSUFFICIENT_STOCK,
                message="Not enough stock for this quantity",
                details=[{"field": "quantity", "type": "insufficient_stock"}],
            )

    @staticmethod
    def _touch(cart: Cart, now: datetime) -> None:
        # Guest carts expire 30 days after their last change (sliding; ADR-040).
        if cart.token_hash is not None:
            cart.expires_at = now + GUEST_CART_TTL
        cart.updated_at = now
