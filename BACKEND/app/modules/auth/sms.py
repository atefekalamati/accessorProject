from __future__ import annotations

import logging
from typing import Protocol, cast

from fastapi import Request

from app.core.config import Environment, Settings, get_app_settings
from app.core.redaction import mask_phone

logger = logging.getLogger("app.sms")


class SmsSender(Protocol):
    async def send_otp(self, mobile: str, code: str) -> None: ...


class FakeSmsSender:
    """In-memory sender for development and tests; tests read codes back from it."""

    def __init__(self) -> None:
        self.sent: dict[str, list[str]] = {}

    async def send_otp(self, mobile: str, code: str) -> None:
        self.sent.setdefault(mobile, []).append(code)
        # Never log the code itself, and only a masked mobile.
        logger.info("sms.otp_sent", extra={"provider": "fake", "mobile": mask_phone(mobile)})

    def last_code(self, mobile: str) -> str | None:
        codes = self.sent.get(mobile)
        return codes[-1] if codes else None


def build_sms_sender(settings: Settings) -> SmsSender:
    """Select the SMS implementation; fails closed in production until OPS-05 (D9)."""
    if settings.environment is Environment.PRODUCTION:
        raise RuntimeError("No real SMS provider is configured for production")
    return FakeSmsSender()


def get_sms_sender(request: Request) -> SmsSender:
    """FastAPI dependency: one sender per application, overridable in tests."""
    sender = getattr(request.app.state, "sms_sender", None)
    if sender is None:
        sender = build_sms_sender(get_app_settings(request))
        request.app.state.sms_sender = sender
    return cast(SmsSender, sender)
