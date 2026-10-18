"""Apply or remove a discount code on the cart (DSC-03, D34, ADR-043).

POST /cart/discount, in one transaction:
1. lock the cart (none → 404); lock the client IP (advisory) so the per-IP count is exact;
2. failed attempts in the window per owner (user, or guest cart), per IP and store-wide:
   any cap reached → 429 with Retry-After, nothing evaluated or recorded;
3. normalize the code (malformed → invalid) and check it against the cart;
4. failure: record the attempt and commit, then 422 (a success never resets the count);
   success: the cart keeps the code. A failure leaves an earlier code in place.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import ColumnElement
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ErrorCode, NotFoundError, RateLimitedError
from app.core.time import utc_now
from app.db.models import Cart, DiscountAttempt, DiscountCode
from app.modules.cart.repository import CartRepository
from app.modules.cart.service import CartOwner
from app.modules.cart.tokens import GUEST_CART_TTL, hash_cart_token
from app.modules.cart.view import line_inputs, load_policy, load_rows, price_with_code
from app.modules.discounts.codes import normalize_code
from app.modules.discounts.repository import DiscountRepository
from app.modules.discounts.rules import Rejection, discount_error, rules_of

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CodeWrite:
    # The guest cookie to re-issue (sliding expiry), if any.
    guest_token: str | None


def _touch(cart: Cart, now: datetime) -> None:
    if cart.token_hash is not None:
        cart.expires_at = now + GUEST_CART_TTL
    cart.updated_at = now


class CartDiscountService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._carts = CartRepository(session)
        self._discounts = DiscountRepository(session)

    async def apply(
        self, owner: CartOwner, raw_code: str, ip: str | None, now: datetime | None = None
    ) -> CodeWrite:
        now = now or utc_now()
        window = timedelta(seconds=self._settings.discount_attempt_window_seconds)
        rejection: Rejection | None = None
        async with self._session.begin():
            cart, token = await self._lock(owner, now)
            if cart is None:
                raise NotFoundError(message="Cart not found")
            if ip is not None:
                await self._discounts.lock_ip(ip)
            await self._check_limits(cart.id, owner.user_id, ip, now, window)
            code, rejection = await self._evaluate(cart.id, owner.user_id, raw_code, now)
            if code is not None and rejection is None:
                cart.discount_code_id = code.id
                _touch(cart, now)
            else:
                await self._discounts.record_failure(
                    cart_id=None if owner.user_id is not None else cart.id,
                    user_id=owner.user_id,
                    ip=ip,
                    now=now,
                    purge_before=now - window,
                )
            await self._session.flush()
        if rejection is not None:
            # Raised after the commit: the failed attempt stays recorded.
            raise discount_error(rejection)
        return CodeWrite(token)

    async def remove(self, owner: CartOwner, now: datetime | None = None) -> CodeWrite:
        """Drop the cart's code; idempotent, and a missing cart is a no-op."""
        now = now or utc_now()
        async with self._session.begin():
            cart, token = await self._lock(owner, now)
            if cart is None:
                return CodeWrite(None)
            if cart.discount_code_id is not None:
                cart.discount_code_id = None
                _touch(cart, now)
                await self._session.flush()
        return CodeWrite(token)

    async def _lock(self, owner: CartOwner, now: datetime) -> tuple[Cart | None, str | None]:
        if owner.user_id is not None:
            return await self._carts.find_user_cart(owner.user_id, lock=True), None
        if owner.guest_token is None:
            return None, None
        cart = await self._carts.find_guest_cart(hash_cart_token(owner.guest_token), now, lock=True)
        return cart, None if cart is None else owner.guest_token

    async def _check_limits(
        self,
        cart_id: UUID,
        user_id: UUID | None,
        ip: str | None,
        now: datetime,
        window: timedelta,
    ) -> None:
        since = now - window
        owner: ColumnElement[bool] = (
            DiscountAttempt.user_id == user_id
            if user_id is not None
            else DiscountAttempt.cart_id == cart_id
        )
        scopes: list[tuple[str, int, tuple[ColumnElement[bool], ...]]] = [
            ("owner", self._settings.discount_max_failed_per_owner, (owner,)),
        ]
        if ip is not None:
            scopes.append(
                ("ip", self._settings.discount_max_failed_per_ip, (DiscountAttempt.ip == ip,))
            )
        scopes.append(("global", self._settings.discount_max_failed_global, ()))
        for scope, cap, criteria in scopes:
            count = await self._discounts.failures(since, cap, *criteria)
            if count.frees_at is None:
                continue
            if scope == "global":
                logger.warning("discount.global_attempt_cap_reached", extra={"cap": cap})
            retry_after = max(1, math.ceil((count.frees_at + window - now).total_seconds()))
            raise RateLimitedError(
                retry_after=retry_after,
                code=ErrorCode.RATE_LIMITED,
                message="Too many failed discount code attempts",
                details=[{"field": "code", "type": f"too_many_attempts_{scope}"}],
            )

    async def _evaluate(
        self, cart_id: UUID, user_id: UUID | None, raw_code: str, now: datetime
    ) -> tuple[DiscountCode | None, Rejection | None]:
        try:
            normalized = normalize_code(raw_code)
        except ValueError:
            return None, Rejection.INVALID
        code = await self._discounts.live_code(normalized)
        if code is None:
            return None, Rejection.INVALID
        rows = await load_rows(self._session, cart_id)
        inputs = line_inputs(rows)
        policy = await load_policy(self._session, bool(inputs))
        usage = await self._discounts.usage_for_user(code.id, user_id)
        _, rejection = price_with_code(inputs, policy, now, rules_of(code), usage)
        return code, rejection
