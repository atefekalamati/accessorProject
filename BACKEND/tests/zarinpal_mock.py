"""A stateful stand-in for the Zarinpal v4 API, served through ``httpx.MockTransport``.

No test ever calls the real sandbox (PAY-07). It follows the documented behaviour:
request opens a session; verify answers 100 once paid, 101 on every later verify, -50
for an amount other than the session's, -51 while unpaid or cancelled, -54 for an
unknown authority; inquiry reports IN_BANK, PAID, VERIFIED, FAILED or REVERSED. Tests
script faults per call (``queue``) or per authority (``verify_codes``).
"""

from __future__ import annotations

import json
import secrets
import string
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Final

import httpx

from app.modules.payments.gateways.zarinpal import (
    INQUIRY_PATH,
    REQUEST_PATH,
    VERIFY_PATH,
    ZarinpalGateway,
)

MERCHANT: Final = "5b3c1f0e-8a2d-4c6b-9e7f-1a2b3c4d5e6f"
CARD_HASH: Final = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
MASKED_PAN: Final = "502229******5995"
_ALPHABET: Final = string.ascii_letters + string.digits

# One scripted answer: an HTTP status with a JSON body, or a transport error to raise.
Scripted = tuple[int, dict[str, Any]] | Exception


def error_body(code: int) -> dict[str, Any]:
    return {"data": [], "errors": {"code": code, "message": f"error {code}", "validations": []}}


@dataclass(slots=True)
class Session:
    amount_rial: int
    # open (at the bank), paid, verified, failed (cancelled), reversed
    status: str = "open"
    ref_id: int = field(default_factory=lambda: 10**11 + secrets.randbelow(10**11))


@dataclass(slots=True)
class ZarinpalMock:
    sessions: dict[str, Session] = field(default_factory=dict)
    # Every call: (path, JSON body).
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    # Per path: answers used, in order, before the normal behaviour.
    queue: dict[str, deque[Scripted]] = field(default_factory=dict)
    # Per authority: a fixed verify error code.
    verify_codes: dict[str, int] = field(default_factory=dict)
    # Error answers' HTTP status (the real one is not documented).
    error_status: int = 200

    def gateway(self, *, sandbox: bool = True, timeout_seconds: float = 5) -> ZarinpalGateway:
        return ZarinpalGateway(
            merchant_id=MERCHANT,
            sandbox=sandbox,
            timeout_seconds=timeout_seconds,
            transport=httpx.MockTransport(self.handle),
        )

    def script(self, path: str, *answers: Scripted) -> None:
        self.queue.setdefault(path, deque()).extend(answers)

    def calls_to(self, path: str) -> list[dict[str, Any]]:
        return [body for called, body in self.calls if called == path]

    # --- the customer at the gateway's page ------------------------------------------------

    def pay(self, authority: str) -> None:
        self.sessions[authority].status = "paid"

    def cancel(self, authority: str) -> None:
        self.sessions[authority].status = "failed"

    # --- the API -------------------------------------------------------------------------

    def handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        path = request.url.path
        self.calls.append((path, body))
        scripted = self.queue.get(path)
        if scripted:
            answer = scripted.popleft()
            if isinstance(answer, Exception):
                raise answer
            status, payload = answer
            return httpx.Response(status, json=payload)
        if body.get("merchant_id") != MERCHANT:
            return self._error(-10)
        if path == REQUEST_PATH:
            return self._request(body, sandbox=request.url.host.startswith("sandbox"))
        if path == VERIFY_PATH:
            return self._verify(body)
        if path == INQUIRY_PATH:
            return self._inquiry(body)
        return httpx.Response(404, json={})

    def _request(self, body: dict[str, Any], *, sandbox: bool) -> httpx.Response:
        authority = ("S" if sandbox else "A") + "".join(
            secrets.choice(_ALPHABET) for _ in range(35)
        )
        self.sessions[authority] = Session(amount_rial=body["amount"])
        data = {
            "code": 100,
            "message": "Success",
            "authority": authority,
            "fee_type": "Merchant",
            "fee": 100,
        }
        return httpx.Response(200, json={"data": data, "errors": []})

    def _verify(self, body: dict[str, Any]) -> httpx.Response:
        authority = body["authority"]
        if authority in self.verify_codes:
            return self._error(self.verify_codes[authority])
        session = self.sessions.get(authority)
        if session is None:
            return self._error(-54)
        if body["amount"] != session.amount_rial:
            return self._error(-50)
        if session.status not in ("paid", "verified"):
            return self._error(-51)
        code = 100 if session.status == "paid" else 101
        session.status = "verified"
        data = {
            "code": code,
            "message": "Verified" if code == 100 else "Already verified",
            "card_hash": CARD_HASH,
            "card_pan": MASKED_PAN,
            "ref_id": session.ref_id,
            "fee_type": "Merchant",
            "fee": 100,
        }
        return httpx.Response(200, json={"data": data, "errors": []})

    def _inquiry(self, body: dict[str, Any]) -> httpx.Response:
        session = self.sessions.get(body["authority"])
        if session is None:
            payload = {"message": "Invalid authority", "errors": {"authority": ["-54"]}}
            return httpx.Response(self.error_status, json=payload)
        status = {
            "open": "IN_BANK",
            "paid": "PAID",
            "verified": "VERIFIED",
            "failed": "FAILED",
            "reversed": "REVERSED",
        }[session.status]
        data = {"code": 100, "message": "Success", "status": status}
        return httpx.Response(200, json={"data": data, "errors": []})

    def _error(self, code: int) -> httpx.Response:
        return httpx.Response(self.error_status, json=error_body(code))
