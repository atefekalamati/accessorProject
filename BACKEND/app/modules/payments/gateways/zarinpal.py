"""The Zarinpal v4 payment gateway (PAY-07, D8, ADR-064).

Official v4 API (zarinpal.com/docs/paymentGateway): JSON ``POST`` to
``/pg/v4/payment/{request,verify,inquiry}.json`` and the customer is sent to
``/pg/StartPay/{authority}``. The customer comes back to ``callback_url`` with
``?Authority=…&Status=OK|NOK``; the frontend result page forwards the authority as the
callback's ``reference`` (ADR-052, ADR-064). ``Status`` is never read: only ``verify``,
server to server with the stored amount, decides.

Money: ``request`` says ``currency: "IRR"`` and sends rial (``toman_to_rial``), so the
gateway's undocumented default unit never matters; ``verify`` takes rial, as documented
(ADR-001). Verify answers no amount;
Zarinpal refuses a verify whose amount differs from the paid one (-50), so 100/101 mean
the stored amount was taken.

Code mapping (verify):
- 100 (first verify), 101 (already verified): PAID with the amount sent.
- -50 (amounts differ): FAILED ``gateway_amount_rejected``, logged ERROR. Nothing was
  settled and Zarinpal returns the money itself, so no refund case (ADR-064).
- -51 (not a paid try): ambiguous between "still at the bank" and "failed or cancelled",
  so ``inquiry`` decides: FAILED/REVERSED are final, anything else stays PENDING.
- -54/-55 (unknown authority): PENDING, never an invented result; reconciliation closes
  it as ``abandoned`` (ADR-051).
- Merchant/terminal codes (-10..-19, -53), transport errors, 5xx and 429:
  ``GatewayUnavailable`` (503; nothing changes).
- An answer without a code (not Zarinpal's JSON): ``GatewayUnavailable`` (an outage).
- Any other code (-9, -52, …): PENDING, logged ERROR, so one broken payment never stops
  a reconciliation round.

``request`` is never retried (it is not idempotent: a retry could open a second
session); ``verify`` and ``inquiry`` are, a bounded number of times. The merchant id and
``card_hash`` are never logged or stored; ``card_pan`` is kept only when masked.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Mapping
from datetime import timedelta
from typing import Any, Final
from uuid import UUID

import httpx

from app.core.time import utc_now
from app.modules.payments.gateways.base import (
    REDACTED,
    GatewayRequest,
    GatewayUnavailable,
    VerifyOutcome,
    VerifyResult,
    redact_payload,
    toman_to_rial,
    valid_reference,
)

ZARINPAL_GATEWAY: Final = "zarinpal"
PRODUCTION_URL: Final = "https://payment.zarinpal.com"
SANDBOX_URL: Final = "https://sandbox.zarinpal.com"
REQUEST_PATH: Final = "/pg/v4/payment/request.json"
VERIFY_PATH: Final = "/pg/v4/payment/verify.json"
INQUIRY_PATH: Final = "/pg/v4/payment/inquiry.json"
START_PAY_PATH: Final = "/pg/StartPay/"
CURRENCY: Final = "IRR"
DESCRIPTION: Final = "Project AK order payment"
# The authority's lifetime is not documented: an inference, checked in the sandbox E2E
# (ADR-064). Only init's "reuse the open session" and reconciliation's abandon rule use it.
SESSION_SECONDS: Final = 15 * 60

CODE_SUCCESS: Final = 100
CODE_VERIFIED: Final = 101
CODE_AMOUNT_REJECTED: Final = -50
CODE_NOT_PAID: Final = -51
UNKNOWN_AUTHORITY: Final = frozenset({-54, -55})
# The merchant or terminal is wrong, blocked or throttled: no payment can be decided.
MERCHANT_CODES: Final = frozenset({-10, -11, -12, -13, -14, -15, -16, -17, -18, -19, -53})

# verify (and its inquiry) share one deadline, this share of the gateway timeout, so the
# adapter answers before the caller's own timeout (``call_gateway``) cuts it off.
BUDGET_SHARE: Final = 0.9
# Attempts and the share of the remaining time each may use; the first gets most of it,
# since verify settles with the bank.
RETRY_SHARES: Final = (0.6, 0.6, 1.0)
RETRY_PAUSE_SECONDS: Final = 0.2
MIN_ATTEMPT_SECONDS: Final = 0.01
_RETRY_STATUS: Final = frozenset({429}) | frozenset(range(500, 600))

_AUTHORITY: Final = re.compile(r"[A-Za-z0-9_-]{1,128}")
_MASKED_PAN: Final = re.compile(r"\d{4,6}\*{2,9}\d{4}")
# An error code written as text: ASCII digits only (``\d`` would also take Persian ones).
_ERROR_CODE: Final = re.compile(r"-[0-9]{1,4}", re.ASCII)
_CALLBACK_KEYS: Final = frozenset({"reference", "status"})
_VERIFY_KEYS: Final = frozenset(
    {"reference", "code", "status", "tracking_code", "card_pan", "fee", "fee_type"}
)

logger = logging.getLogger(__name__)


class _Retryable(Exception):
    """A transport error, a timeout, 429 or 5xx: worth another attempt."""


class ZarinpalGateway:
    name = ZARINPAL_GATEWAY

    def __init__(
        self,
        *,
        merchant_id: str,
        sandbox: bool,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._merchant_id = merchant_id
        self._base_url = SANDBOX_URL if sandbox else PRODUCTION_URL
        self._timeout = timeout_seconds
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            transport=transport,
            headers={"Accept": "application/json"},
            timeout=timeout_seconds,
            follow_redirects=False,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    # --- PaymentGateway ------------------------------------------------------------------

    async def request(self, *, payment_id: UUID, amount: int, callback_url: str) -> GatewayRequest:
        body = {
            "merchant_id": self._merchant_id,
            "amount": toman_to_rial(amount),
            "currency": CURRENCY,
            "description": DESCRIPTION,
            "callback_url": callback_url,
            # The payment id only: no customer data goes to the gateway.
            "metadata": {"order_id": str(payment_id)},
        }
        try:
            answer = await self._send(REQUEST_PATH, body, self._timeout)
        except _Retryable as error:
            raise GatewayUnavailable(str(error)) from None
        code, data = _code(answer), _data(answer)
        authority = data.get("authority")
        if (
            code != CODE_SUCCESS
            or not isinstance(authority, str)
            or not _AUTHORITY.fullmatch(authority)
        ):
            level = logging.ERROR if code in MERCHANT_CODES or code is None else logging.WARNING
            logger.log(
                level,
                "payment.zarinpal_request_refused",
                extra={"payment_id": str(payment_id), "code": code},
            )
            raise GatewayUnavailable(f"zarinpal request answered code {code}")
        return GatewayRequest(
            reference=authority,
            redirect_url=f"{self._base_url}{START_PAY_PATH}{authority}",
            expires_at=utc_now() + timedelta(seconds=SESSION_SECONDS),
        )

    async def verify(self, *, reference: str, amount: int) -> VerifyResult:
        body = {
            "merchant_id": self._merchant_id,
            # Rial, as documented for verify (no currency field there); request said IRR.
            "amount": toman_to_rial(amount),
            "authority": reference,
        }
        deadline = asyncio.get_running_loop().time() + self._timeout * BUDGET_SHARE
        answer = await self._send_with_retry(VERIFY_PATH, body, deadline)
        code, data = _code(answer), _data(answer)
        if code is None:
            # No Zarinpal answer at all (a maintenance page, a proxy error, ``{}``): an
            # outage, so reconciliation's "gateway down" rule applies, not a per-payment one.
            logger.error("payment.zarinpal_unreadable_answer", extra={"reference": reference})
            raise GatewayUnavailable("zarinpal verify answer has no code")
        raw = _raw(reference, code, data)
        if code in (CODE_SUCCESS, CODE_VERIFIED):
            return VerifyResult(VerifyOutcome.PAID, amount=amount, raw=raw)
        if code == CODE_AMOUNT_REJECTED:
            logger.error(
                "payment.zarinpal_amount_rejected",
                extra={"reference": reference, "amount": amount},
            )
            return VerifyResult(
                VerifyOutcome.FAILED, failure_reason="gateway_amount_rejected", raw=raw
            )
        if code == CODE_NOT_PAID:
            return await self._inquire(reference, raw, deadline)
        if code in UNKNOWN_AUTHORITY:
            logger.warning(
                "payment.zarinpal_unknown_authority", extra={"reference": reference, "code": code}
            )
            return VerifyResult(VerifyOutcome.PENDING, raw=raw)
        if code in MERCHANT_CODES:
            logger.error(
                "payment.zarinpal_merchant_refused", extra={"reference": reference, "code": code}
            )
            raise GatewayUnavailable(f"zarinpal verify answered code {code}")
        logger.error(
            "payment.zarinpal_unexpected_answer", extra={"reference": reference, "code": code}
        )
        return VerifyResult(VerifyOutcome.PENDING, raw=raw)

    def parse_callback(self, payload: Mapping[str, Any]) -> str | None:
        reference = valid_reference(payload.get("reference"))
        return reference if reference is not None and _AUTHORITY.fullmatch(reference) else None

    def redact_callback(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return redact_payload(payload, _CALLBACK_KEYS)

    # --- internals -----------------------------------------------------------------------

    async def _inquire(self, reference: str, raw: dict[str, Any], deadline: float) -> VerifyResult:
        """After -51: FAILED only when the gateway says so; otherwise not decided yet."""
        body = {"merchant_id": self._merchant_id, "authority": reference}
        try:
            answer = await self._send_with_retry(INQUIRY_PATH, body, deadline)
        except GatewayUnavailable:
            # Verify answered a moment ago; the next callback or round decides.
            logger.warning("payment.zarinpal_inquiry_unavailable", extra={"reference": reference})
            return VerifyResult(VerifyOutcome.PENDING, raw=raw)
        status = _data(answer).get("status")
        raw = raw | redact_payload({"status": status}, _VERIFY_KEYS)
        if status == "FAILED":
            return VerifyResult(VerifyOutcome.FAILED, failure_reason="declined", raw=raw)
        if status == "REVERSED":
            return VerifyResult(VerifyOutcome.FAILED, failure_reason="reversed", raw=raw)
        if status in ("PAID", "VERIFIED"):
            # Verify said "not paid" a moment ago: a race or a gateway fault; retry later.
            logger.error(
                "payment.zarinpal_inquiry_disagrees",
                extra={"reference": reference, "status": status},
            )
        elif status != "IN_BANK":
            logger.error(
                "payment.zarinpal_unexpected_answer",
                extra={"reference": reference, "code": _code(answer)},
            )
        return VerifyResult(VerifyOutcome.PENDING, raw=raw)

    async def _send_with_retry(
        self, path: str, body: dict[str, Any], deadline: float
    ) -> dict[str, Any]:
        """Bounded retries until ``deadline`` (loop time); then ``GatewayUnavailable``."""
        loop = asyncio.get_running_loop()
        last = "no time left"
        for attempt, share in enumerate(RETRY_SHARES):
            if attempt:
                # A short pause, never more than a quarter of the time left.
                await asyncio.sleep(min(RETRY_PAUSE_SECONDS, (deadline - loop.time()) / 4))
            remaining = deadline - loop.time()
            if remaining <= MIN_ATTEMPT_SECONDS:
                break
            try:
                return await self._send(path, body, remaining * share)
            except _Retryable as error:
                last = str(error)
                logger.warning(
                    "payment.zarinpal_retry",
                    extra={"path": path, "attempt": attempt + 1, "error": last},
                )
        raise GatewayUnavailable(f"zarinpal {path}: {last}")

    async def _send(self, path: str, body: dict[str, Any], seconds: float) -> dict[str, Any]:
        """One call: the JSON object answer (any HTTP status but 429/5xx), or ``_Retryable``.

        ``seconds`` bounds the whole call (httpx's own timeout is per phase). Errors name
        the exception type only and drop its context: the httpx request carries the
        merchant id in its body, and error trackers walk ``__context__``.
        """
        try:
            async with asyncio.timeout(seconds):
                response = await self._client.post(path, json=body, timeout=seconds)
        except (httpx.HTTPError, TimeoutError, RuntimeError) as error:
            if isinstance(error, RuntimeError) and not self._client.is_closed:
                raise  # a bug, not an outage; only a closed client (shutdown) is one
            retryable = _Retryable(type(error).__name__)
            retryable.__context__ = None
            raise retryable from None
        if response.status_code in _RETRY_STATUS:
            raise _Retryable(f"HTTP {response.status_code}")
        try:
            answer = response.json()
        except ValueError:
            answer = None
        return answer if isinstance(answer, dict) else {}


def _data(answer: Mapping[str, Any]) -> dict[str, Any]:
    data = answer.get("data")
    return data if isinstance(data, dict) else {}


def _code(answer: Mapping[str, Any]) -> int | None:
    """``data.code`` on success; on errors the code in ``errors``, in any documented shape.

    The error body is not fully documented. The v4 docs show ``errors`` as an object
    (``{"code": -9, …}`` or, in the inquiry example, ``{"authority": ["…", "-54"]}``)
    while the inquiry output table calls it an array, so an array of such objects
    (``[{"code": -51, …}]``) is read too. The real shape is recorded in the sandbox E2E.
    """
    code = _data(answer).get("code")
    # Success (100, 101) only from a real integer ``data.code``, as Zarinpal sends it.
    if isinstance(code, int) and not isinstance(code, bool):
        return code
    errors = answer.get("errors")
    for entry in errors if isinstance(errors, list) else [errors]:
        if isinstance(entry, dict):
            code = _error_code(entry)
            if code is not None:
                return code
    return None


def _error_code(errors: Mapping[str, Any]) -> int | None:
    code = _as_code(errors.get("code"))
    if code is not None:
        return code
    for messages in errors.values():
        if isinstance(messages, list):
            for message in messages:
                code = _as_code(message)
                if code is not None:
                    return code
    return None


def _as_code(value: object) -> int | None:
    """An error code in ``errors``: negative only (so never 100/101), int or "-54"."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value if value < 0 else None
    if isinstance(value, str) and _ERROR_CODE.fullmatch(value.strip()):
        return int(value)
    return None


def _raw(reference: str, code: int | None, data: Mapping[str, Any]) -> dict[str, Any]:
    """The verify answer kept on the payment: allowlisted, PAN only masked, no card_hash."""
    kept: dict[str, Any] = {"reference": reference, "code": code}
    ref_id = data.get("ref_id")
    if isinstance(ref_id, int | str) and not isinstance(ref_id, bool):
        kept["tracking_code"] = str(ref_id)
    pan = data.get("card_pan")
    if pan is not None:
        kept["card_pan"] = pan if isinstance(pan, str) and _MASKED_PAN.fullmatch(pan) else REDACTED
    for key in ("fee", "fee_type"):
        if key in data:
            kept[key] = data[key]
    return redact_payload(kept, _VERIFY_KEYS)
