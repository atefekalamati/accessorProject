"""Contracts every external-provider adapter must meet (OPS-10, ADR-009, ADR-058).

Payment gateway, SMS sender and file storage sit behind interfaces with fakes for
development and tests. The real adapters (PAY-07, OPS-05, OPS-07) are deferred; when one
is written it is added to the matching ``*_IMPLEMENTATIONS`` list and must pass the same
tests. The last section locks what production does until then: it refuses the fakes.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Environment, MediaStorage, Settings
from app.main import create_app
from app.modules.auth.sms import FakeSmsSender, SmsSender, build_sms_sender
from app.modules.payments.gateways import build_payment_gateway
from app.modules.payments.gateways.base import PaymentGateway, VerifyOutcome, valid_reference
from app.modules.payments.gateways.fake import FakeGateway
from app.shared.storage import (
    FileStorage,
    InMemoryFileStorage,
    LocalFileStorage,
    create_file_storage,
    new_storage_key,
)

BASE_URL = "https://cdn.example.com/media"
MOBILE = "+989121234567"
CARD = "6037991234567890"

# --- file storage --------------------------------------------------------------------------

StorageFactory = Callable[[Path], FileStorage]
STORAGE_IMPLEMENTATIONS: dict[str, StorageFactory] = {
    "local": lambda root: LocalFileStorage(root, BASE_URL),
    "memory": lambda _root: InMemoryFileStorage(BASE_URL),
}


@pytest.fixture(params=sorted(STORAGE_IMPLEMENTATIONS))
def storage(request: pytest.FixtureRequest, tmp_path: Path) -> FileStorage:
    return STORAGE_IMPLEMENTATIONS[request.param](tmp_path)


async def test_storage_saves_overwrites_and_deletes_idempotently(storage: FileStorage) -> None:
    key = new_storage_key("webp")

    await storage.save(key, b"one")
    await storage.save(key, b"two")  # same key again: replaced, not an error
    await storage.delete(key)
    await storage.delete(key)  # a missing file is not an error


async def test_storage_urls_are_built_by_the_server(storage: FileStorage) -> None:
    key = new_storage_key("png")

    assert storage.url(key) == f"{BASE_URL}/{key}"


@pytest.mark.parametrize("key", ["../x.png", "a" * 32 + ".gif", "/etc/passwd", "A" * 32 + ".png"])
async def test_storage_refuses_keys_it_did_not_make(storage: FileStorage, key: str) -> None:
    with pytest.raises(ValueError):
        await storage.save(key, b"x")
    with pytest.raises(ValueError):
        await storage.delete(key)
    with pytest.raises(ValueError):
        storage.url(key)


# --- SMS ---------------------------------------------------------------------------------------

SMS_IMPLEMENTATIONS: dict[str, Callable[[], SmsSender]] = {"fake": FakeSmsSender}


@pytest.mark.parametrize("name", sorted(SMS_IMPLEMENTATIONS))
async def test_sms_sends_without_logging_the_code_or_the_full_mobile(
    name: str, caplog: pytest.LogCaptureFixture
) -> None:
    sender = SMS_IMPLEMENTATIONS[name]()

    with caplog.at_level(logging.DEBUG):
        await sender.send_otp(MOBILE, "482913")

    logged = " ".join(f"{record.getMessage()} {record.__dict__}" for record in caplog.records)
    assert "482913" not in logged
    assert MOBILE not in logged


# --- payment gateway --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GatewayUnderTest:
    gateway: PaymentGateway
    # Makes the customer finish (paid=True) or abandon the payment at the gateway.
    settle: Callable[[str, bool], Awaitable[object]]


async def _fake(engine: AsyncEngine) -> GatewayUnderTest:
    fake = FakeGateway(engine, base_url="https://shop.example.com/pay", session_seconds=900)
    return GatewayUnderTest(fake, lambda reference, paid: fake.complete(reference, paid=paid))


GATEWAY_IMPLEMENTATIONS: dict[str, Callable[[AsyncEngine], Awaitable[GatewayUnderTest]]] = {
    "fake": _fake,
}


@pytest_asyncio.fixture(params=sorted(GATEWAY_IMPLEMENTATIONS))
async def gateway(
    request: pytest.FixtureRequest, db_engine: AsyncEngine
) -> AsyncIterator[GatewayUnderTest]:
    yield await GATEWAY_IMPLEMENTATIONS[request.param](db_engine)


@pytest.mark.integration
async def test_gateway_request_gives_a_reference_and_a_redirect(
    gateway: GatewayUnderTest,
) -> None:
    started = datetime.now(UTC)

    request = await gateway.gateway.request(
        payment_id=uuid4(), amount=150_000, callback_url="https://shop.example.com/cb"
    )

    assert gateway.gateway.name
    assert valid_reference(request.reference) == request.reference
    assert request.redirect_url.startswith(("https://", "http://"))
    assert request.expires_at.tzinfo is not None and request.expires_at > started


@pytest.mark.integration
async def test_gateway_reports_paid_only_after_payment_with_the_amount_taken(
    gateway: GatewayUnderTest,
) -> None:
    request = await gateway.gateway.request(
        payment_id=uuid4(), amount=150_000, callback_url="https://shop.example.com/cb"
    )

    before = await gateway.gateway.verify(reference=request.reference, amount=150_000)
    await gateway.settle(request.reference, True)
    after = await gateway.gateway.verify(reference=request.reference, amount=150_000)

    assert before.outcome is VerifyOutcome.PENDING
    assert (after.outcome, after.amount) == (VerifyOutcome.PAID, 150_000)


@pytest.mark.integration
async def test_gateway_never_reports_paid_for_an_abandoned_or_unknown_payment(
    gateway: GatewayUnderTest,
) -> None:
    request = await gateway.gateway.request(
        payment_id=uuid4(), amount=90_000, callback_url="https://shop.example.com/cb"
    )
    await gateway.settle(request.reference, False)

    abandoned = await gateway.gateway.verify(reference=request.reference, amount=90_000)
    unknown = await gateway.gateway.verify(reference=f"NOPE-{uuid4().hex}", amount=90_000)

    assert abandoned.outcome is VerifyOutcome.FAILED
    assert unknown.outcome is not VerifyOutcome.PAID


@pytest.mark.integration
async def test_gateway_callbacks_are_parsed_and_redacted_safely(
    gateway: GatewayUnderTest,
) -> None:
    adapter = gateway.gateway

    assert adapter.parse_callback({}) is None
    assert adapter.parse_callback({"reference": "has space"}) is None
    redacted = adapter.redact_callback({"reference": "R-1", "card": CARD, "note": f"pan {CARD}"})

    assert CARD not in str(redacted)
    assert all(isinstance(value, str | int | bool) or value is None for value in redacted.values())


# --- production refuses the fakes (until PAY-07, OPS-05 and OPS-07; ADR-058) ------------------


def _production(settings: Settings) -> Settings:
    return settings.model_copy(update={"environment": Environment.PRODUCTION})


def test_production_builds_no_payment_gateway(settings: Settings) -> None:
    with pytest.raises(RuntimeError, match="No real payment gateway"):
        build_payment_gateway(_production(settings), None)  # type: ignore[arg-type]


async def test_production_does_not_start_while_reconciling_without_a_gateway(
    settings: Settings,
) -> None:
    production = _production(settings).model_copy(update={"payment_reconcile_seconds": 60})
    application = create_app(production)

    with pytest.raises(RuntimeError, match="No real payment gateway"):
        async with application.router.lifespan_context(application):
            pass  # pragma: no cover - startup must fail


def test_production_builds_no_sms_sender(settings: Settings) -> None:
    with pytest.raises(RuntimeError, match="No real SMS provider"):
        build_sms_sender(_production(settings))


def test_production_refuses_in_memory_storage() -> None:
    values = {
        "database_url": "postgresql+asyncpg://user:password@localhost:5432/project_ak",
        "jwt_secret": "x" * 40,
        "otp_hash_secret": "y" * 40,
        "otp_mock_enabled": False,
        "cors_origins": ["https://shop.example.com"],
        "media_public_base_url": BASE_URL,
        "media_allowed_hosts": ["cdn.example.com"],
        "environment": Environment.PRODUCTION,
    }
    Settings(_env_file=None, **values)  # type: ignore[arg-type]  # local storage is accepted

    with pytest.raises(ValidationError, match="MEDIA_STORAGE=memory is forbidden"):
        Settings(_env_file=None, **values, media_storage=MediaStorage.MEMORY)  # type: ignore[arg-type]


def test_the_storage_factory_picks_the_configured_implementation(
    settings: Settings, tmp_path: Path
) -> None:
    local = settings.model_copy(
        update={"media_storage": MediaStorage.LOCAL, "media_root": tmp_path}
    )

    assert isinstance(create_file_storage(settings), InMemoryFileStorage)
    assert isinstance(create_file_storage(local), LocalFileStorage)
