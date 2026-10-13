from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.auth.dependencies import get_optional_user
from app.modules.auth.service import CurrentUser
from app.modules.cart.service import CartOwner, CartService
from app.modules.cart.tokens import CART_COOKIE_NAME, parse_cart_token
from app.modules.cart.view import CartView


def get_cart_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CartService:
    return CartService(session)


def get_cart_view(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CartView:
    return CartView(session)


async def get_cart_owner(
    user: Annotated[CurrentUser | None, Depends(get_optional_user)],
    cart_token: Annotated[str | None, Cookie(alias=CART_COOKIE_NAME)] = None,
) -> CartOwner:
    """A signed-in user acts on their own cart and the guest cookie is ignored (it is
    merged at login, CART-04). Otherwise the request acts for the cookie's guest cart."""
    if user is not None:
        return CartOwner(user_id=user.id, guest_token=None)
    return CartOwner(user_id=None, guest_token=parse_cart_token(cart_token))
