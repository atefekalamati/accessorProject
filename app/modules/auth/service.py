from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ErrorCode, RateLimitedError
from app.core.redaction import mask_phone
from app.core.time import utc_now
from app.db.models import OtpCode
from app.modules.auth.otp import generate_otp_code, hash_otp_code, otp_hash_key
from app.modules.auth.repository import OtpRepository, WindowUsage
from app.modules.auth.schemas import RequestOtpResponse
from app.modules.auth.sms import SmsSender

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
