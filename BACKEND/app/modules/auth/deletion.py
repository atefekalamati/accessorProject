"""Account deletion: anonymize the identity, keep orders for accounting (ACC-05, D37).

PRD «پروفایل» ✓, ADR-062, ADR-063 (A1, A3; A2 is the redemption digest of DSC-06).
The account row stays (orders reference it, RESTRICT) but loses its name, email and
mobile, so the mobile is free for a new account that sees none of the old orders.

Lock order: the user's carts → the user's orders (id order) → the user row, all
``FOR UPDATE``. Placing an order locks the cart first and only then touches the user row
(FK key-share), and creating a return locks the order first: both come before the user
row, so a deletion serializes with them instead of deadlocking. Either the order or
return exists and the deletion is refused (409), or the cart is gone (nothing to place)
and the account is deleted before the return insert re-checks it.
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from fastapi import Request
from sqlalchemy import delete, exists, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import (
    BusinessRuleError,
    ConflictError,
    ErrorCode,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
)
from app.core.time import utc_now
from app.db.models import (
    Address,
    Cart,
    CartItem,
    ContactMessage,
    IdempotencyKey,
    OrderAddress,
    OtpCode,
    OtpPurpose,
    Payment,
    PaymentStatus,
    ReturnRequest,
    User,
    UserSession,
    UserStatus,
)
from app.db.models.orders import Order, OrderStatus
from app.modules.auth.otp import otp_hash_key, verify_otp_code
from app.modules.auth.repository import OtpRepository, UserRepository
from app.modules.auth.service import CUSTOMER_ROLE
from app.modules.returns.state import OPEN_STATUSES
from app.shared.audit import record_audit

logger = logging.getLogger(__name__)


def _active_orders() -> ConflictError:
    return ConflictError(
        code=ErrorCode.ACCOUNT_HAS_ACTIVE_ORDERS,
        message="Finish or cancel your open orders and returns before deleting the account",
    )


def _otp_invalid() -> UnauthorizedError:
    # As at login: one error for wrong, expired, exhausted, consumed or login codes.
    return UnauthorizedError(code=ErrorCode.OTP_INVALID, message="Invalid or expired code")


class AccountDeletionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._otps = OtpRepository(session)

    async def precheck(self, user_id: UUID) -> str:
        """The account's mobile when it may be deleted now (before a code is sent)."""
        async with self._session.begin():
            user = await self.lock_deletable(user_id)
            if user.phone is None:  # only a deleted account has none
                raise NotFoundError(message="User not found")
            return user.phone

    async def confirm(
        self, user_id: UUID, code: str, settings: Settings, request: Request | None
    ) -> None:
        """Delete the account with a valid ``account_delete`` code (ACC-06).

        Preconditions first, so a refused deletion consumes no code; a wrong code counts
        as an attempt (committed before the 401), as at login.
        """
        key = otp_hash_key(settings)
        deleted = False
        async with self._session.begin():
            # Unlocked read: the mobile never changes (PATCH /users/me refuses it, SEC-03);
            # the row is locked below, after the OTP advisory lock.
            mobile = await self._session.scalar(select(User.phone).where(User.id == user_id))
            if mobile is None:
                raise NotFoundError(message="User not found")
            # The OTP lock first, as request-otp and login take it (no code issued meanwhile).
            await self._otps.lock_mobile(mobile)
            user = await self.lock_deletable(user_id)
            otp = await self._otps.lock_latest_unconsumed(mobile, OtpPurpose.ACCOUNT_DELETE)
            now = utc_now()
            if otp is not None and _code_ok(otp, code, mobile, key, settings, now):
                if await self._otps.consume(otp.id, now):
                    await self.anonymize_locked(user, request)
                    deleted = True
        if not deleted:
            logger.info("user.deletion_otp_rejected", extra={"user_id": str(user_id)})
            raise _otp_invalid()

    async def lock_deletable(self, user_id: UUID) -> User:
        """The user row, locked, once every precondition holds (caller's transaction).

        Staff (any role but customer) → 422 ``STAFF_ACCOUNT``; open orders, payments or
        returns → 409 ``ACCOUNT_HAS_ACTIVE_ORDERS``. Nothing is written.
        """
        if not self._session.in_transaction():
            raise RuntimeError("AccountDeletionService needs the caller's transaction")
        await self._session.execute(
            select(Cart.id).where(Cart.user_id == user_id).order_by(Cart.id).with_for_update()
        )
        await self._session.execute(
            select(Order.id).where(Order.user_id == user_id).order_by(Order.id).with_for_update()
        )
        user = await self._users.lock_active(user_id)
        if user is None:
            raise NotFoundError(message="User not found")
        if user.status != UserStatus.ACTIVE:
            # A blocked account keeps its number, so it cannot re-register (ADR-017).
            raise ForbiddenError(message="Account is not active")
        roles = set(await self._users.role_names(user.id))
        if roles - {CUSTOMER_ROLE}:
            raise BusinessRuleError(
                code=ErrorCode.STAFF_ACCOUNT,
                message="A staff account is deleted only after a super admin removes its roles",
            )
        if await self._has_open_business(user.id):
            raise _active_orders()
        return user

    async def anonymize_locked(self, user: User, request: Request | None) -> None:
        """Remove the identity of a user ``lock_deletable`` returned, in one transaction."""
        now = utc_now()
        phone = user.phone
        user_id = user.id

        order_ids = select(Order.id).where(Order.user_id == user_id).scalar_subquery()
        await self._session.execute(
            update(Order).where(Order.user_id == user_id).values(phone=None, updated_at=now)
        )
        await self._session.execute(
            update(OrderAddress)
            .where(OrderAddress.order_id.in_(order_ids))
            .values(
                recipient_name=None,
                phone=None,
                postal_code=None,
                address_line=None,
                plaque=None,
                unit=None,
                source_address_id=None,
            )
        )
        await self._session.execute(
            update(ContactMessage)
            .where(ContactMessage.user_id == user_id)
            .values(name=None, phone=None, email=None, updated_at=now)
        )
        await self._session.execute(delete(Address).where(Address.user_id == user_id))
        # Stored replies of POST /orders and returns hold the address and mobile; the
        # account can send no request any more, so nothing is left to replay.
        await self._session.execute(delete(IdempotencyKey).where(IdempotencyKey.user_id == user_id))
        carts = select(Cart.id).where(Cart.user_id == user_id).scalar_subquery()
        await self._session.execute(delete(CartItem).where(CartItem.cart_id.in_(carts)))
        await self._session.execute(delete(Cart).where(Cart.user_id == user_id))
        if phone is not None:
            await self._session.execute(delete(OtpCode).where(OtpCode.mobile == phone))
        await self._session.execute(
            update(UserSession)
            .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )

        user.phone = None
        user.first_name = None
        user.last_name = None
        user.email = None
        user.mobile_verified_at = None
        user.deleted_at = now
        await self._session.flush()
        # Ids only: no name, mobile or email (CLAUDE.md §8, ADR-059).
        await record_audit(
            self._session,
            actor_id=user_id,
            action="user.deleted",
            entity_type="user",
            entity_id=user_id,
            before={"deleted": False},
            after={"deleted": True},
            request=request,
        )
        logger.info("user.deleted", extra={"user_id": str(user_id)})

    async def _has_open_business(self, user_id: UUID) -> bool:
        mine = Order.user_id == user_id
        open_order = exists().where(
            mine,
            or_(
                Order.status == OrderStatus.PENDING_PAYMENT,
                # Confirmed until delivered (then completed): still on its way.
                Order.status == OrderStatus.CONFIRMED,
            ),
        )
        open_payment = exists().where(
            Payment.order_id == Order.id,
            mine,
            Payment.status.in_((PaymentStatus.PENDING, PaymentStatus.REFUND_REQUIRED)),
        )
        open_return = exists().where(
            ReturnRequest.user_id == user_id,
            ReturnRequest.status.in_([status.value for status in OPEN_STATUSES]),
        )
        found = await self._session.scalar(select(or_(open_order, open_payment, open_return)))
        return bool(found)


def _code_ok(
    otp: OtpCode, code: str, mobile: str, key: bytes, settings: Settings, now: datetime
) -> bool:
    """The same checks and attempt counting as the login code (ADR-016)."""
    max_attempts = settings.otp_max_attempts
    if otp.expires_at <= now or otp.attempt_count >= max_attempts:
        return False
    if verify_otp_code(code, mobile, key, otp.code_hash):
        return True
    otp.attempt_count += 1
    if otp.attempt_count >= max_attempts:
        otp.expires_at = now  # expire, never mark consumed
    return False
