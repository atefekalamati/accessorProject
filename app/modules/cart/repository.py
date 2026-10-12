"""Cart rows (CART-01, ADR-040).

Every write to a cart runs under ``FOR UPDATE`` on its ``carts`` row, so two requests on
one cart (two tabs, a double click) never interleave. Lock order for cart writes:
cart → variant (read only) → nothing else; stock is read, never locked (adding to a cart
reserves nothing, ADR-007).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Cart, CartItem, CartStatus
from app.modules.cart.tokens import GUEST_CART_TTL


class CartRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_user_cart(self, user_id: UUID) -> Cart:
        """The user's active cart, created if missing, under FOR UPDATE.

        ``ON CONFLICT DO NOTHING`` on the partial unique index makes concurrent first
        writes create one cart.
        """
        await self._session.execute(
            insert(Cart)
            .values(user_id=user_id, status=CartStatus.ACTIVE)
            .on_conflict_do_nothing(
                index_elements=["user_id"],
                index_where=(Cart.status == CartStatus.ACTIVE) & Cart.user_id.is_not(None),
            )
        )
        statement = (
            select(Cart)
            .where(Cart.user_id == user_id, Cart.status == CartStatus.ACTIVE)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return (await self._session.scalars(statement)).one()

    async def find_user_cart(self, user_id: UUID) -> Cart | None:
        statement = select(Cart).where(Cart.user_id == user_id, Cart.status == CartStatus.ACTIVE)
        return (await self._session.scalars(statement)).one_or_none()

    async def find_guest_cart(
        self, token_hash: str, now: datetime, *, lock: bool = False
    ) -> Cart | None:
        """The active, unexpired guest cart of a token."""
        statement = select(Cart).where(
            Cart.token_hash == token_hash,
            Cart.status == CartStatus.ACTIVE,
            Cart.expires_at > now,
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await self._session.scalars(statement)).one_or_none()

    async def create_guest_cart(self, token_hash: str, now: datetime) -> Cart:
        cart = Cart(
            token_hash=token_hash, status=CartStatus.ACTIVE, expires_at=now + GUEST_CART_TTL
        )
        self._session.add(cart)
        await self._session.flush()
        return cart

    async def items(self, cart_id: UUID) -> list[CartItem]:
        """Lines in a stable order, by line id (ADR-031: same cart → same price split)."""
        statement = select(CartItem).where(CartItem.cart_id == cart_id).order_by(CartItem.id)
        return list(await self._session.scalars(statement))

    async def item(self, cart_id: UUID, item_id: UUID) -> CartItem | None:
        statement = select(CartItem).where(CartItem.id == item_id, CartItem.cart_id == cart_id)
        return (await self._session.scalars(statement)).one_or_none()

    async def line_count(self, cart_id: UUID) -> int:
        statement = select(func.count()).select_from(CartItem).where(CartItem.cart_id == cart_id)
        return int(await self._session.scalar(statement) or 0)
