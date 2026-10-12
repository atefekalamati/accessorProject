from __future__ import annotations

import logging
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Any, Final
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.core.config import Settings
from app.core.errors import ErrorCode, ForbiddenError, RateLimitedError, UnauthorizedError
from app.core.redaction import mask_email, mask_phone
from app.core.time import utc_now
from app.db.models import OtpCode, User, UserSession, UserStatus
from app.modules.auth.otp import (
    generate_otp_code,
    hash_otp_code,
    otp_hash_key,
    verify_otp_code,
)
from app.modules.auth.repository import (
    OtpRepository,
    SessionRepository,
    UserRepository,
    WindowUsage,
)
from app.modules.auth.schemas import ProfileResponse, RequestOtpResponse
from app.modules.auth.sms import SmsSender
from app.modules.auth.tokens import (
    AccessTokenError,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_refresh_token,
)
from app.shared.audit import record_audit

logger = logging.getLogger("app.auth")

RATE_WINDOW = timedelta(hours=1)


def _seconds_until(moment: datetime, now: datetime) -> int:
    return max(1, math.ceil((moment - now).total_seconds()))


def _rate_limited(retry_after: int) -> RateLimitedError:
    return RateLimitedError(
        code=ErrorCode.OTP_RATE_LIMITED,
        message="Too many OTP requests",
        retry_after=retry_after,
    )


def _window_exceeded(usage: WindowUsage, limit: int, now: datetime) -> RateLimitedError | None:
    if usage.count < limit:
        return None
    oldest = usage.oldest or now
    return _rate_limited(_seconds_until(oldest + RATE_WINDOW, now))


class OtpService:
    def __init__(
        self,
        session: AsyncSession,
        repository: OtpRepository,
        sms_sender: SmsSender,
        settings: Settings,
    ) -> None:
        self._session = session
        self._repository = repository
        self._sms_sender = sms_sender
        self._settings = settings

    async def request_otp(self, mobile: str, ip: str | None) -> RequestOtpResponse:
        """Issue and send a new OTP for an already-normalized mobile.

        The response never depends on whether a user exists for ``mobile``.
        """
        settings = self._settings
        key = otp_hash_key(settings)
        code = generate_otp_code(settings)

        async with self._session.begin():
            await self._repository.lock_mobile(mobile)
            now = utc_now()
            await self._enforce_limits(mobile, ip, now)
            await self._repository.expire_active(mobile, now)
            await self._repository.add(
                OtpCode(
                    mobile=mobile,
                    code_hash=hash_otp_code(code, mobile, key),
                    expires_at=now + timedelta(seconds=settings.otp_ttl_seconds),
                    ip=ip,
                    created_at=now,
                )
            )

        # Send only after commit, so every delivered code exists in the database.
        await self._sms_sender.send_otp(mobile, code)
        logger.info("otp.requested", extra={"mobile": mask_phone(mobile)})
        return RequestOtpResponse(
            expires_in_seconds=settings.otp_ttl_seconds,
            resend_after_seconds=settings.otp_resend_cooldown_seconds,
        )

    async def _enforce_limits(self, mobile: str, ip: str | None, now: datetime) -> None:
        settings = self._settings
        since = now - RATE_WINDOW

        latest = await self._repository.latest_created_at(mobile)
        if latest is not None:
            resend_at = latest + timedelta(seconds=settings.otp_resend_cooldown_seconds)
            if resend_at > now:
                raise _rate_limited(_seconds_until(resend_at, now))

        mobile_usage = await self._repository.usage_by_mobile(mobile, since)
        error = _window_exceeded(mobile_usage, settings.otp_max_per_mobile_per_hour, now)
        if error is not None:
            raise error

        if ip is not None:
            ip_usage = await self._repository.usage_by_ip(ip, since)
            error = _window_exceeded(ip_usage, settings.otp_max_per_ip_per_hour, now)
            if error is not None:
                raise error

        global_usage = await self._repository.usage_global(since)
        error = _window_exceeded(global_usage, settings.otp_max_global_per_hour, now)
        if error is not None:
            logger.warning(
                "otp.global_cap_hit",
                extra={"count": global_usage.count, "cap": settings.otp_max_global_per_hour},
            )
            raise error


CUSTOMER_ROLE = "customer"
USER_AGENT_MAX_LENGTH = 512


@dataclass(frozen=True, slots=True)
class ClientInfo:
    ip: str | None
    user_agent: str | None


@dataclass(frozen=True, slots=True)
class IssuedTokens:
    """Transport-neutral result; the router decides where each token goes (ADR-012)."""

    access_token: str
    access_expires_in_seconds: int
    refresh_token: str
    refresh_expires_at: datetime


class _Outcome(Enum):
    OK = auto()
    INVALID = auto()
    FORBIDDEN = auto()


def _otp_invalid() -> UnauthorizedError:
    # One error for wrong, expired, exhausted and consumed codes: nothing to enumerate.
    return UnauthorizedError(code=ErrorCode.OTP_INVALID, message="Invalid or expired code")


def _session_invalid() -> UnauthorizedError:
    return UnauthorizedError(message="Invalid or expired session")


def _can_log_in(user: User | None) -> bool:
    return user is not None and not user.is_deleted and user.status == UserStatus.ACTIVE


class AuthService:
    """OTP verification, login sessions and refresh-token rotation."""

    def __init__(
        self,
        session: AsyncSession,
        otp_repository: OtpRepository,
        user_repository: UserRepository,
        session_repository: SessionRepository,
        settings: Settings,
    ) -> None:
        self._session = session
        self._otps = otp_repository
        self._users = user_repository
        self._sessions = session_repository
        self._settings = settings

    async def verify_otp(
        self, mobile: str, code: str, client: ClientInfo, audit_request: Request | None
    ) -> IssuedTokens:
        """Consume a valid OTP for an already-normalized mobile and open a session.

        Failed attempts are committed before the error is raised, so the attempt
        counter survives the 401.
        """
        key = otp_hash_key(self._settings)
        tokens: IssuedTokens | None = None
        async with self._session.begin():
            # Same lock as request-otp: no new code is issued mid-verification.
            await self._otps.lock_mobile(mobile)
            otp = await self._otps.lock_latest_unconsumed(mobile)
            now = utc_now()
            outcome = self._check_otp(otp, code, mobile, key, now)
            if otp is not None and outcome is _Outcome.OK:
                if not await self._otps.consume(otp.id, now):
                    outcome = _Outcome.INVALID
            if outcome is _Outcome.OK:
                user, created = await self._resolve_user(mobile, now)
                if user is None:
                    outcome = _Outcome.FORBIDDEN
                else:
                    tokens, user_session = await self._open_session(user.id, uuid4(), client, now)
                    await record_audit(
                        self._session,
                        actor_id=user.id,
                        action="auth.login",
                        entity_type="user",
                        entity_id=user.id,
                        before=None,
                        after={"session_id": user_session.id, "user_created": created},
                        request=audit_request,
                    )

        if outcome is _Outcome.FORBIDDEN:
            logger.warning("auth.login_denied", extra={"mobile": mask_phone(mobile)})
            raise ForbiddenError(message="Account is not active")
        if tokens is None:
            logger.info("auth.otp_rejected", extra={"mobile": mask_phone(mobile)})
            raise _otp_invalid()
        logger.info("auth.login", extra={"mobile": mask_phone(mobile)})
        return tokens

    async def refresh(
        self, refresh_token: str, client: ClientInfo, audit_request: Request | None
    ) -> IssuedTokens:
        """Rotate a refresh token; reuse of a revoked one revokes its whole family."""
        tokens: IssuedTokens | None = None
        reused_family: UUID | None = None
        async with self._session.begin():
            current = await self._sessions.lock_by_token_hash(hash_refresh_token(refresh_token))
            now = utc_now()
            if current is not None and current.revoked_at is not None:
                reused_family = current.family_id
                revoked = await self._sessions.revoke_family(current.family_id, now)
                await record_audit(
                    self._session,
                    actor_id=None,
                    action="auth.refresh_reuse",
                    entity_type="user",
                    entity_id=current.user_id,
                    before=None,
                    after={
                        "family_id": current.family_id,
                        "session_id": current.id,
                        "revoked_sessions": revoked,
                    },
                    request=audit_request,
                )
            elif current is not None and current.expires_at > now:
                current.revoked_at = now
                if _can_log_in(await self._users.get(current.user_id)):
                    tokens, _ = await self._open_session(
                        current.user_id, current.family_id, client, now
                    )

        if reused_family is not None:
            logger.warning("auth.refresh_reuse", extra={"family_id": str(reused_family)})
        if tokens is None:
            raise _session_invalid()
        return tokens

    async def logout(self, refresh_token: str, audit_request: Request | None) -> None:
        """Revoke the session of ``refresh_token``; unknown or revoked tokens are a no-op.

        Unlike refresh, presenting a revoked token here is not treated as reuse, so a
        repeated logout stays idempotent.
        """
        async with self._session.begin():
            current = await self._sessions.lock_by_token_hash(hash_refresh_token(refresh_token))
            if current is None or current.revoked_at is not None:
                return
            now = utc_now()
            # Rotation already revoked the older sessions of the family; revoking the
            # whole family also covers any session left active (ADR-017).
            await self._sessions.revoke_family(current.family_id, now)
            await record_audit(
                self._session,
                actor_id=current.user_id,
                action="auth.logout",
                entity_type="user",
                entity_id=current.user_id,
                before=None,
                after={"session_id": current.id, "family_id": current.family_id},
                request=audit_request,
            )
        logger.info("auth.logout", extra={"session_id": str(current.id)})

    def _check_otp(
        self, otp: OtpCode | None, code: str, mobile: str, key: bytes, now: datetime
    ) -> _Outcome:
        max_attempts = self._settings.otp_max_attempts
        if otp is None or otp.expires_at <= now or otp.attempt_count >= max_attempts:
            return _Outcome.INVALID
        if verify_otp_code(code, mobile, key, otp.code_hash):
            return _Outcome.OK
        otp.attempt_count += 1
        if otp.attempt_count >= max_attempts:
            # Same invalidation as request-otp: expire, never mark consumed (ADR-016).
            otp.expires_at = now
        return _Outcome.INVALID

    async def _resolve_user(self, mobile: str, now: datetime) -> tuple[User | None, bool]:
        """The active account of ``mobile``, created on first login; None when denied."""
        user = await self._users.get_by_phone(mobile)
        if user is not None:
            if not _can_log_in(user):
                return None, False
            if user.mobile_verified_at is None:
                user.mobile_verified_at = now
            return user, False

        # Deleting a blocked account must not unblock its mobile (ADR-017).
        if await self._users.has_deleted_blocked(mobile):
            return None, False
        role_id = await self._users.role_id(CUSTOMER_ROLE)
        if role_id is None:
            raise RuntimeError("The customer role is missing; run python -m app.db.seed")
        user = User(phone=mobile, status=UserStatus.ACTIVE, mobile_verified_at=now)
        await self._users.add_with_role(user, role_id)
        return user, True

    async def _open_session(
        self, user_id: UUID, family_id: UUID, client: ClientInfo, now: datetime
    ) -> tuple[IssuedTokens, UserSession]:
        settings = self._settings
        refresh_token = generate_refresh_token()
        user_agent = client.user_agent[:USER_AGENT_MAX_LENGTH] if client.user_agent else None
        user_session = UserSession(
            id=uuid4(),
            user_id=user_id,
            family_id=family_id,
            refresh_token_hash=hash_refresh_token(refresh_token),
            user_agent=user_agent,
            ip=client.ip,
            expires_at=now + timedelta(days=settings.refresh_token_ttl_days),
            created_at=now,
        )
        await self._sessions.add(user_session)
        tokens = IssuedTokens(
            access_token=create_access_token(user_id, user_session.id, settings, now),
            access_expires_in_seconds=settings.access_token_ttl_seconds,
            refresh_token=refresh_token,
            refresh_expires_at=user_session.expires_at,
        )
        return tokens, user_session


@dataclass(frozen=True, slots=True)
class CurrentUser:
    """The authenticated user of one request, loaded from the database (never the token)."""

    id: UUID
    session_id: UUID
    status: str
    roles: frozenset[str]
    permissions: frozenset[str]


def _not_authenticated() -> UnauthorizedError:
    return UnauthorizedError(
        message="Authentication required", headers={"WWW-Authenticate": "Bearer"}
    )


class AccessService:
    """Resolves an access token to the current user; runs on every authenticated request."""

    def __init__(
        self, session: AsyncSession, user_repository: UserRepository, settings: Settings
    ) -> None:
        self._session = session
        self._users = user_repository
        self._settings = settings

    async def authenticate(self, access_token: str) -> CurrentUser:
        """Validate the token, then re-check user, session and permissions in the database.

        The token only identifies the user and session; status, soft delete, session
        revocation and permissions are read fresh each time (ADR-017).
        """
        try:
            claims = decode_access_token(access_token, self._settings)
        except AccessTokenError:
            raise _not_authenticated() from None

        # A short transaction of its own, so services can begin() on the same session.
        async with self._session.begin():
            row = await self._users.get_with_session(claims.user_id, claims.session_id)
            now = utc_now()
            if row is None:
                raise _not_authenticated()
            user, user_session = row
            # Logout and rotation revoke the session, so its access tokens die with it.
            if (
                user.is_deleted
                or user_session.revoked_at is not None
                or user_session.expires_at <= now
            ):
                raise _not_authenticated()
            if user.status != UserStatus.ACTIVE:
                raise ForbiddenError(message="Account is not active")
            roles = await self._users.role_names(user.id)
            permissions = await self._users.permission_keys(user.id)

        return CurrentUser(
            id=user.id,
            session_id=user_session.id,
            status=user.status,
            roles=frozenset(roles),
            permissions=frozenset(permissions),
        )


PROFILE_FIELDS: Final = ("first_name", "last_name", "email")


class ProfileService:
    """Read and edit the current user's own profile."""

    def __init__(self, session: AsyncSession, user_repository: UserRepository) -> None:
        self._session = session
        self._users = user_repository

    async def get_profile(self, current: CurrentUser) -> ProfileResponse:
        async with self._session.begin():
            user = await self._users.get(current.id)
        if user is None or user.is_deleted:
            raise _not_authenticated()
        return _profile(user, current)

    async def update_profile(
        self, current: CurrentUser, changes: Mapping[str, Any], audit_request: Request | None
    ) -> ProfileResponse:
        """Apply validated ``changes`` (a subset of PROFILE_FIELDS); audit real changes only."""
        async with self._session.begin():
            user = await self._users.lock_active(current.id)
            if user is None:
                raise _not_authenticated()
            before = {field: getattr(user, field) for field in PROFILE_FIELDS}
            changed = {
                field: value
                for field, value in changes.items()
                if field in PROFILE_FIELDS and before[field] != value
            }
            if changed:
                for field, value in changed.items():
                    setattr(user, field, value)
                await self._session.flush()
                await record_audit(
                    self._session,
                    actor_id=user.id,
                    action="user.profile_updated",
                    entity_type="user",
                    entity_id=user.id,
                    before={field: before[field] for field in changed},
                    after=changed,
                    request=audit_request,
                    # redact() masks phones and secrets, not emails.
                    field_masks={"email": mask_email},
                )
        return _profile(user, current)


def _profile(user: User, current: CurrentUser) -> ProfileResponse:
    return ProfileResponse(
        id=user.id,
        mobile=user.phone,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        status=user.status,
        mobile_verified_at=user.mobile_verified_at,
        roles=sorted(current.roles),
        permissions=sorted(current.permissions),
    )
