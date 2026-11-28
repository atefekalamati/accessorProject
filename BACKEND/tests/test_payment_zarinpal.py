"""The Zarinpal v4 adapter against a mocked API (PAY-07, ADR-064); no database, no network."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from pydantic import SecretStr
from zarinpal_mock import CARD_HASH, MASKED_PAN, MERCHANT, ZarinpalMock, error_body

from app.core.config import Environment, PaymentGatewayName, Settings
from app.core.time import utc_now
from app.modules.payments.gateways import build_payment_gateway, close_payment_gateway
from app.modules.payments.gateways.base import GatewayUnavailable, VerifyOutcome
from app.modules.payments.gateways.zarinpal import (
    INQUIRY_PATH,
    PRODUCTION_URL,
    REQUEST_PATH,
    SANDBOX_URL,
    SESSION_SECONDS,
    VERIFY_PATH,
    ZarinpalGateway,
)
from app.modules.payments.service import call_gateway

CALLBACK = "https://shop.example.com/checkout/result"
AMOUNT = 150_000  # toman


@pytest.fixture
def mock() -> ZarinpalMock:
    return ZarinpalMock()


@pytest_asyncio.fixture
async def gateway(mock: ZarinpalMock) -> AsyncIterator[ZarinpalGateway]:
    adapter = mock.gateway()
    yield adapter
    await close_payment_gateway(adapter)


async def _start(gateway: ZarinpalGateway, amount: int = AMOUNT) -> str:
    started = await gateway.request(payment_id=uuid4(), amount=amount, callback_url=CALLBACK)
    return started.reference


def _ok(**data: Any) -> tuple[int, dict[str, Any]]:
    return 200, {"data": {"code": 100, "message": "Success"} | data, "errors": []}


# --- request -------------------------------------------------------------------------------


async def test_request_sends_rial_with_the_currency_and_no_customer_data(
    mock: ZarinpalMock, gateway: ZarinpalGateway
) -> None:
    payment_id = uuid4()
    before = utc_now()

    started = await gateway.request(payment_id=payment_id, amount=AMOUNT, callback_url=CALLBACK)
    after = utc_now()

    [body] = mock.calls_to(REQUEST_PATH)
    assert body == {
        "merchant_id": MERCHANT,
        "amount": AMOUNT * 10,
        "currency": "IRR",
        "description": "Project AK order payment",
        "callback_url": CALLBACK,
        "metadata": {"order_id": str(payment_id)},
    }
    assert started.reference.startswith("S") and len(started.reference) == 36
    assert started.redirect_url == f"{SANDBOX_URL}/pg/StartPay/{started.reference}"
    lifetime = timedelta(seconds=SESSION_SECONDS)
    assert before + lifetime <= started.expires_at <= after + lifetime


async def test_production_host_outside_the_sandbox(mock: ZarinpalMock) -> None:
    started = await mock.gateway(sandbox=False).request(
        payment_id=uuid4(), amount=AMOUNT, callback_url=CALLBACK
    )

    assert started.reference.startswith("A")
    assert started.redirect_url.startswith(f"{PRODUCTION_URL}/pg/StartPay/")


@pytest.mark.parametrize(
    "answer",
    [
        (503, {}),
        (429, {}),
        httpx.ConnectError("refused"),
        httpx.ReadTimeout("slow"),
    ],
)
async def test_request_is_never_retried(
    mock: ZarinpalMock, gateway: ZarinpalGateway, answer: Any
) -> None:
    mock.script(REQUEST_PATH, answer)

    with pytest.raises(GatewayUnavailable):
        await _start(gateway)

    assert len(mock.calls_to(REQUEST_PATH)) == 1  # a retry could open a second session


@pytest.mark.parametrize(
    "answer",
    [
        (200, error_body(-10)),
        (422, error_body(-9)),
        (200, {"data": {"code": 100, "authority": "has space"}, "errors": []}),
        (200, {"data": {"code": 100}, "errors": []}),
        (200, {"unexpected": True}),
    ],
)
async def test_a_refused_or_broken_request_is_unavailable(
    mock: ZarinpalMock,
    gateway: ZarinpalGateway,
    answer: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    mock.script(REQUEST_PATH, answer)

    with caplog.at_level(logging.DEBUG), pytest.raises(GatewayUnavailable):
        await _start(gateway)

    assert any(r.getMessage() == "payment.zarinpal_request_refused" for r in caplog.records)
    assert MERCHANT not in caplog.text


async def test_a_non_json_answer_is_unavailable_or_pending() -> None:
    def broken(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>maintenance</html>")

    adapter = ZarinpalGateway(
        merchant_id=MERCHANT,
        sandbox=True,
        timeout_seconds=5,
        transport=httpx.MockTransport(broken),
    )

    try:
        with pytest.raises(GatewayUnavailable):
            await _start(adapter)
        # Not Zarinpal's JSON at all: an outage, never a per-payment answer.
        with pytest.raises(GatewayUnavailable):
            await adapter.verify(reference="S" + "x" * 35, amount=AMOUNT)
    finally:
        await close_payment_gateway(adapter)


# --- verify --------------------------------------------------------------------------------


async def test_a_paid_session_verifies_once_then_101_with_the_same_rial_amount(
    mock: ZarinpalMock, gateway: ZarinpalGateway
) -> None:
    reference = await _start(gateway)
    mock.pay(reference)

    first = await gateway.verify(reference=reference, amount=AMOUNT)
    again = await gateway.verify(reference=reference, amount=AMOUNT)

    assert (first.outcome, first.amount) == (VerifyOutcome.PAID, AMOUNT)
    assert (again.outcome, again.amount) == (VerifyOutcome.PAID, AMOUNT)
    assert (first.raw["code"], again.raw["code"]) == (100, 101)
    [request] = mock.calls_to(REQUEST_PATH)
    verifies = mock.calls_to(VERIFY_PATH)
    assert {body["amount"] for body in verifies} == {request["amount"]} == {AMOUNT * 10}
    assert verifies[0] == {"merchant_id": MERCHANT, "amount": AMOUNT * 10, "authority": reference}
    ref_id = mock.sessions[reference].ref_id
    assert first.raw == {
        "reference": reference,
        "code": 100,
        "tracking_code": str(ref_id),
        "card_pan": MASKED_PAN,
        "fee": 100,
        "fee_type": "Merchant",
    }
    assert CARD_HASH not in str(first.raw) and MERCHANT not in str(first.raw)


async def test_an_amount_the_gateway_rejects_fails_without_a_refund_case(
    mock: ZarinpalMock, gateway: ZarinpalGateway, caplog: pytest.LogCaptureFixture
) -> None:
    reference = await _start(gateway)
    mock.pay(reference)

    with caplog.at_level(logging.ERROR, logger="app.modules.payments.gateways.zarinpal"):
        result = await gateway.verify(reference=reference, amount=AMOUNT + 1)

    assert (result.outcome, result.failure_reason) == (
        VerifyOutcome.FAILED,
        "gateway_amount_rejected",
    )
    assert result.amount is None and result.raw["code"] == -50
    [record] = [r for r in caplog.records if r.getMessage() == "payment.zarinpal_amount_rejected"]
    assert record.levelno == logging.ERROR


@pytest.mark.parametrize(
    ("customer", "outcome", "reason"),
    [
        ("still_at_bank", VerifyOutcome.PENDING, None),
        ("cancelled", VerifyOutcome.FAILED, "declined"),
        ("reversed", VerifyOutcome.FAILED, "reversed"),
    ],
)
async def test_not_paid_asks_inquiry_whether_it_is_final(
    mock: ZarinpalMock,
    gateway: ZarinpalGateway,
    customer: str,
    outcome: VerifyOutcome,
    reason: str | None,
) -> None:
    reference = await _start(gateway)
    if customer == "cancelled":
        mock.cancel(reference)
    elif customer == "reversed":
        mock.sessions[reference].status = "reversed"

    result = await gateway.verify(reference=reference, amount=AMOUNT)

    assert (result.outcome, result.failure_reason) == (outcome, reason)
    assert mock.calls_to(INQUIRY_PATH) == [{"merchant_id": MERCHANT, "authority": reference}]
    assert result.raw["code"] == -51 and "status" in result.raw


@pytest.mark.parametrize(
    "inquiry",
    [
        _ok(status="PAID"),
        _ok(status="VERIFIED"),
        _ok(status="SOMETHING_NEW"),
        (200, error_body(-52)),
        (503, {}),
        httpx.ConnectError("down"),
    ],
)
async def test_an_unsure_inquiry_never_fails_the_payment(
    mock: ZarinpalMock, gateway: ZarinpalGateway, inquiry: Any
) -> None:
    reference = await _start(gateway)
    mock.script(VERIFY_PATH, (200, error_body(-51)))
    mock.script(INQUIRY_PATH, inquiry, inquiry, inquiry)

    result = await gateway.verify(reference=reference, amount=AMOUNT)

    assert result.outcome is VerifyOutcome.PENDING


@pytest.mark.parametrize("code", [-54, -55])
async def test_an_unknown_authority_is_pending_never_invented(
    mock: ZarinpalMock, gateway: ZarinpalGateway, code: int
) -> None:
    mock.script(VERIFY_PATH, (200, error_body(code)))

    result = await gateway.verify(reference="S" + "0" * 35, amount=AMOUNT)

    assert result.outcome is VerifyOutcome.PENDING


async def test_the_inquiry_error_shape_with_field_messages_is_understood(
    mock: ZarinpalMock, gateway: ZarinpalGateway
) -> None:
    mock.script(VERIFY_PATH, (422, {"errors": {"authority": ["Invalid authority.", "-54"]}}))

    result = await gateway.verify(reference="S" + "0" * 35, amount=AMOUNT)

    assert (result.outcome, result.raw["code"]) == (VerifyOutcome.PENDING, -54)


@pytest.mark.parametrize(
    ("errors", "outcome"),
    [
        # The documented object shapes …
        ({"code": -51, "message": "not paid"}, "inquiry"),
        ({"authority": ["Invalid authority.", "-54"]}, VerifyOutcome.PENDING),
        # … and the array the inquiry table describes.
        ([{"code": -51, "message": "not paid"}], "inquiry"),
        ([{"code": "-54", "message": "Invalid authority."}], VerifyOutcome.PENDING),
        ([{"authority": ["Invalid authority.", "-54"]}], VerifyOutcome.PENDING),
        ([{"message": "no code"}, {"code": -50}], VerifyOutcome.FAILED),
    ],
)
async def test_both_error_shapes_are_understood(
    mock: ZarinpalMock, gateway: ZarinpalGateway, errors: Any, outcome: Any
) -> None:
    reference = await _start(gateway)
    mock.cancel(reference)  # an inquiry, if asked, says FAILED
    mock.script(VERIFY_PATH, (422, {"data": [], "errors": errors}))

    result = await gateway.verify(reference=reference, amount=AMOUNT)

    if outcome == "inquiry":
        assert (result.outcome, result.raw["code"]) == (VerifyOutcome.FAILED, -51)
        assert len(mock.calls_to(INQUIRY_PATH)) == 1
    else:
        # The exact code was read, not just some code with the same outcome.
        expected = -50 if outcome is VerifyOutcome.FAILED else -54
        assert (result.outcome, result.raw["code"]) == (outcome, expected)
        assert mock.calls_to(INQUIRY_PATH) == []


@pytest.mark.parametrize(
    "body",
    [
        {"data": [], "errors": []},
        {"data": [], "errors": [{"message": "no code"}]},
        {"data": [], "errors": ["-51"]},
        {"data": [], "errors": {"code": True}},
        # Never PAID from an error body, a non-ASCII digit or a string data.code.
        {"data": [], "errors": {"code": 100}},
        {"data": [], "errors": [{"code": 101}]},
        {"data": [], "errors": {"a": ["100"]}},
        {"data": [], "errors": {"a": ["-۵۱"]}},
        {"data": {"code": "100"}, "errors": []},
    ],
)
async def test_an_error_without_a_readable_code_is_an_outage(
    mock: ZarinpalMock, gateway: ZarinpalGateway, body: Any
) -> None:
    mock.script(VERIFY_PATH, (422, body))

    with pytest.raises(GatewayUnavailable):
        await gateway.verify(reference="S" + "0" * 35, amount=AMOUNT)


@pytest.mark.parametrize("code", [-10, -11, -12, -14, -19, -53])
async def test_a_merchant_or_terminal_problem_is_unavailable(
    mock: ZarinpalMock, gateway: ZarinpalGateway, code: int, caplog: pytest.LogCaptureFixture
) -> None:
    mock.script(VERIFY_PATH, (200, error_body(code)))

    with caplog.at_level(logging.ERROR), pytest.raises(GatewayUnavailable):
        await gateway.verify(reference="S" + "0" * 35, amount=AMOUNT)

    assert any(r.getMessage() == "payment.zarinpal_merchant_refused" for r in caplog.records)
    assert len(mock.calls_to(VERIFY_PATH)) == 1  # a decided answer is not retried


@pytest.mark.parametrize(
    "answer",
    [
        (200, error_body(-9)),
        (200, error_body(-52)),
        (422, {"data": [], "errors": {"code": "-52", "message": "unexpected"}}),
    ],
)
async def test_a_per_payment_error_is_pending_so_reconciliation_goes_on(
    mock: ZarinpalMock, gateway: ZarinpalGateway, answer: Any, caplog: pytest.LogCaptureFixture
) -> None:
    mock.script(VERIFY_PATH, answer)

    with caplog.at_level(logging.ERROR):
        result = await gateway.verify(reference="S" + "0" * 35, amount=AMOUNT)

    assert result.outcome is VerifyOutcome.PENDING
    assert any(r.getMessage() == "payment.zarinpal_unexpected_answer" for r in caplog.records)


@pytest.mark.parametrize(
    "answer", [(200, {"data": [], "errors": []}), (400, {}), (403, {"message": "blocked"})]
)
async def test_an_answer_without_a_code_is_an_outage(
    mock: ZarinpalMock, gateway: ZarinpalGateway, answer: Any
) -> None:
    mock.script(VERIFY_PATH, answer)

    with pytest.raises(GatewayUnavailable):
        await gateway.verify(reference="S" + "0" * 35, amount=AMOUNT)


async def test_a_slow_inquiry_ends_before_the_callers_timeout(mock: ZarinpalMock) -> None:
    """verify and its inquiry share one deadline inside the caller's ``call_gateway``."""

    async def slow(request: httpx.Request) -> httpx.Response:
        if request.url.path == INQUIRY_PATH:
            await asyncio.sleep(5)
        return mock.handle(request)

    adapter = ZarinpalGateway(
        merchant_id=MERCHANT,
        sandbox=True,
        timeout_seconds=1,
        transport=httpx.MockTransport(slow),
    )
    try:
        reference = await _start(adapter)
        result = await call_gateway(adapter.verify(reference=reference, amount=AMOUNT), 1)
    finally:
        await close_payment_gateway(adapter)

    # Its own fallback (not decided yet), not the caller's timeout (503).
    assert result.outcome is VerifyOutcome.PENDING


async def test_verify_retries_a_few_times_then_succeeds(
    mock: ZarinpalMock, gateway: ZarinpalGateway
) -> None:
    reference = await _start(gateway)
    mock.pay(reference)
    mock.script(VERIFY_PATH, httpx.ConnectError("reset"), (502, {}))

    result = await gateway.verify(reference=reference, amount=AMOUNT)

    assert result.outcome is VerifyOutcome.PAID
    assert len(mock.calls_to(VERIFY_PATH)) == 3


@pytest.mark.parametrize("answer", [(503, {}), (429, {}), httpx.ReadTimeout("slow")])
async def test_verify_gives_up_after_three_attempts(
    mock: ZarinpalMock, gateway: ZarinpalGateway, answer: Any
) -> None:
    mock.script(VERIFY_PATH, answer, answer, answer, answer)

    with pytest.raises(GatewayUnavailable):
        await gateway.verify(reference="S" + "0" * 35, amount=AMOUNT)

    assert len(mock.calls_to(VERIFY_PATH)) == 3


async def test_retries_stop_at_the_timeout_budget(mock: ZarinpalMock) -> None:
    gateway = mock.gateway(timeout_seconds=0.1)
    mock.script(VERIFY_PATH, (503, {}), (503, {}), (503, {}))
    loop = asyncio.get_running_loop()
    started = loop.time()

    try:
        with pytest.raises(GatewayUnavailable):
            await gateway.verify(reference="S" + "0" * 35, amount=AMOUNT)
    finally:
        await close_payment_gateway(gateway)

    # The pauses shrink with the time left: the whole call ends inside its budget.
    assert loop.time() - started < 0.1
    assert 1 <= len(mock.calls_to(VERIFY_PATH)) <= 3


async def test_an_unmasked_card_number_is_never_kept(
    mock: ZarinpalMock, gateway: ZarinpalGateway
) -> None:
    mock.script(VERIFY_PATH, _ok(card_pan="5022291234565995", ref_id=7, card_hash=CARD_HASH))

    result = await gateway.verify(reference="S" + "0" * 35, amount=AMOUNT)

    assert result.raw["card_pan"] == "[REDACTED]"
    assert "5022291234565995" not in str(result.raw) and CARD_HASH not in str(result.raw)


# --- callback ------------------------------------------------------------------------------


def test_the_callback_reference_is_the_forwarded_authority(gateway: ZarinpalGateway) -> None:
    authority = "S" + "a1B2" * 8 + "xyz"

    assert gateway.parse_callback({"reference": authority, "status": "OK"}) == authority
    assert gateway.parse_callback({"Authority": authority}) is None  # the contract is frozen
    assert gateway.parse_callback({"reference": "../StartPay"}) is None
    assert gateway.parse_callback({"reference": 42}) is None
    redacted = gateway.redact_callback(
        {"reference": authority, "status": "NOK", "card": "6037991234567890"}
    )
    assert redacted == {"reference": authority, "status": "NOK"}


# --- the merchant id stays secret ----------------------------------------------------------


async def test_the_merchant_id_is_never_logged_on_any_path(
    mock: ZarinpalMock, gateway: ZarinpalGateway, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        reference = await _start(gateway)
        await gateway.verify(reference=reference, amount=AMOUNT)  # -51, inquiry
        mock.pay(reference)
        await gateway.verify(reference=reference, amount=AMOUNT + 5)  # -50
        await gateway.verify(reference=reference, amount=AMOUNT)
        for code in (-9, -52, -54):
            mock.script(VERIFY_PATH, (200, error_body(code)))
            await gateway.verify(reference=reference, amount=AMOUNT)
        mock.script(VERIFY_PATH, httpx.ConnectError(f"merchant {MERCHANT}"), (200, error_body(-11)))
        with pytest.raises(GatewayUnavailable):
            await gateway.verify(reference=reference, amount=AMOUNT)
        mock.script(REQUEST_PATH, (200, error_body(-10)))
        with pytest.raises(GatewayUnavailable):
            await _start(gateway)

    assert any(r.getMessage() == "payment.zarinpal_retry" for r in caplog.records)
    assert MERCHANT not in caplog.text
    assert all(MERCHANT not in str(vars(record)) for record in caplog.records)
    assert CARD_HASH not in caplog.text


# --- building it ---------------------------------------------------------------------------


def _zarinpal(settings: Settings, merchant: str | None = MERCHANT) -> Settings:
    return settings.model_copy(
        update={
            "payment_gateway": PaymentGatewayName.ZARINPAL,
            "zarinpal_merchant_id": SecretStr(merchant) if merchant is not None else None,
        }
    )


async def test_build_gives_a_sandbox_zarinpal_by_default(settings: Settings) -> None:
    gateway = build_payment_gateway(_zarinpal(settings), None)  # type: ignore[arg-type]
    live_settings = _zarinpal(settings).model_copy(update={"zarinpal_sandbox": False})
    live = build_payment_gateway(live_settings, None)  # type: ignore[arg-type]

    assert isinstance(gateway, ZarinpalGateway) and gateway.name == "zarinpal"
    assert isinstance(live, ZarinpalGateway)
    assert (gateway._base_url, live._base_url) == (SANDBOX_URL, PRODUCTION_URL)
    await close_payment_gateway(gateway)
    await close_payment_gateway(live)


@pytest.mark.parametrize("merchant", [None, "", "not-a-merchant", MERCHANT + "0"])
def test_build_refuses_a_missing_or_malformed_merchant_id(
    settings: Settings, merchant: str | None
) -> None:
    with pytest.raises(RuntimeError, match="ZARINPAL_MERCHANT_ID") as error:
        build_payment_gateway(_zarinpal(settings, merchant), None)  # type: ignore[arg-type]

    assert merchant is None or merchant == "" or merchant not in str(error.value)


@pytest.mark.parametrize("sandbox", [True, False])
def test_production_refuses_zarinpal_until_go_live(settings: Settings, sandbox: bool) -> None:
    production = _zarinpal(settings).model_copy(
        update={"environment": Environment.PRODUCTION, "zarinpal_sandbox": sandbox}
    )

    with pytest.raises(RuntimeError, match="production"):
        build_payment_gateway(production, None)  # type: ignore[arg-type]


async def test_close_releases_the_client_and_ignores_gateways_without_one(
    gateway: ZarinpalGateway,
) -> None:
    await close_payment_gateway(gateway)
    await close_payment_gateway(object())

    with pytest.raises(GatewayUnavailable):  # a closed client is an outage, never a 500
        await _start(gateway)


# --- settings ------------------------------------------------------------------------------


def _load(**values: Any) -> Settings:
    """Settings from the environment only (no .env file), as the application loads them."""
    values = {
        "database_url": "postgresql+asyncpg://user:password@localhost:5432/project_ak",
        "jwt_secret": "test-secret-that-is-at-least-32-characters",
    } | values
    return Settings(_env_file=None, **values)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name in ("PAYMENT_PROVIDER", "PAYMENT_GATEWAY", "ZARINPAL_MERCHANT_ID", "ZARINPAL_SANDBOX"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


@pytest.mark.parametrize("variable", ["PAYMENT_PROVIDER", "PAYMENT_GATEWAY"])
def test_the_provider_is_read_from_either_variable(
    clean_env: pytest.MonkeyPatch, variable: str
) -> None:
    clean_env.setenv(variable, "zarinpal")
    clean_env.setenv("ZARINPAL_MERCHANT_ID", MERCHANT)

    loaded = _load()

    assert loaded.payment_gateway is PaymentGatewayName.ZARINPAL
    assert loaded.zarinpal_sandbox is True
    assert loaded.zarinpal_merchant_id is not None
    assert MERCHANT not in repr(loaded)


@pytest.mark.parametrize("keyword", ["payment_provider", "payment_gateway"])
def test_the_provider_keyword_is_never_silently_dropped(
    clean_env: pytest.MonkeyPatch, keyword: str
) -> None:
    loaded = _load(**{keyword: "zarinpal"})

    assert loaded.payment_gateway is PaymentGatewayName.ZARINPAL


def test_an_explicit_provider_wins_over_the_environment(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("PAYMENT_PROVIDER", "zarinpal")

    # Either keyword beats the environment (scripts/export_openapi.py relies on it).
    assert _load(payment_provider="fake").payment_gateway is PaymentGatewayName.FAKE
    assert _load(payment_gateway="fake").payment_gateway is PaymentGatewayName.FAKE


def test_two_variables_naming_different_gateways_are_refused(
    clean_env: pytest.MonkeyPatch,
) -> None:
    clean_env.setenv("PAYMENT_PROVIDER", "zarinpal")
    clean_env.setenv("PAYMENT_GATEWAY", "fake")

    with pytest.raises(ValueError, match="PAYMENT_PROVIDER and PAYMENT_GATEWAY"):
        _load()

    clean_env.setenv("PAYMENT_GATEWAY", "zarinpal")
    assert _load().payment_gateway is PaymentGatewayName.ZARINPAL
