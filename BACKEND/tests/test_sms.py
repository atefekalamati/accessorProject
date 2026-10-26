from __future__ import annotations

import logging
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import Environment, Settings
from app.main import create_app
from app.modules.auth.sms import FakeSmsSender, SmsSender, build_sms_sender, get_sms_sender

MOBILE = "+989121234567"


async def test_fake_sender_keeps_codes_in_memory() -> None:
    sender = FakeSmsSender()

    await sender.send_otp(MOBILE, "000042")
    await sender.send_otp(MOBILE, "123456")

    assert sender.sent == {MOBILE: ["000042", "123456"]}
    assert sender.last_code(MOBILE) == "123456"
    assert sender.last_code("+989121234568") is None


async def test_fake_sender_never_logs_code_or_full_mobile(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="app.sms"):
        await FakeSmsSender().send_otp(MOBILE, "987654")

    assert caplog.records
    logged = " ".join(f"{record.getMessage()} {record.__dict__}" for record in caplog.records)
    assert "987654" not in logged
    assert MOBILE not in logged


def test_fake_sender_is_selected_outside_production(settings: Settings) -> None:
    assert isinstance(build_sms_sender(settings), FakeSmsSender)


def test_production_without_real_provider_fails_closed(settings: Settings) -> None:
    production = settings.model_copy(update={"environment": Environment.PRODUCTION})

    with pytest.raises(RuntimeError, match="No real SMS provider"):
        build_sms_sender(production)


def _sender_probe_app(settings: Settings) -> FastAPI:
    application = create_app(settings)

    @application.get("/sms-probe")
    async def probe(sender: Annotated[SmsSender, Depends(get_sms_sender)]) -> dict[str, str]:
        await sender.send_otp(MOBILE, "000042")
        return {"sender": type(sender).__name__}

    return application


async def test_dependency_reuses_one_sender_per_app(settings: Settings) -> None:
    application = _sender_probe_app(settings)

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://testserver"
    ) as client:
        await client.get("/sms-probe")
        response = await client.get("/sms-probe")

    assert response.json() == {"sender": "FakeSmsSender"}
    assert application.state.sms_sender.sent == {MOBILE: ["000042", "000042"]}


async def test_dependency_can_be_overridden(settings: Settings) -> None:
    application = _sender_probe_app(settings)
    replacement = FakeSmsSender()
    application.dependency_overrides[get_sms_sender] = lambda: replacement

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://testserver"
    ) as client:
        await client.get("/sms-probe")

    assert replacement.last_code(MOBILE) == "000042"
    assert getattr(application.state, "sms_sender", None) is None
