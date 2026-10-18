"""Own addresses: CRUD, ownership, one default, the cap (ADDR-01, ADR-045)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from conftest import MakeAccount
from httpx import AsyncClient, Response
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.time import utc_now
from app.db.models import Address
from app.modules.addresses.service import MAX_ADDRESSES

pytestmark = pytest.mark.integration

URL = "/api/v1/addresses"
BODY: dict[str, Any] = {
    "recipient_name": "Sara Ahmadi",
    "phone": "0912 123 4567",
    "province": "Tehran",
    "city": "Tehran",
    "postal_code": "1234567890",
    "address_line": "Valiasr St, No. 10",
}


@pytest_asyncio.fixture(autouse=True)
async def _addresses_go_first(
    db_engine: AsyncEngine, make_account: MakeAccount
) -> AsyncIterator[None]:
    """addresses.user_id is RESTRICT: remove this test's addresses before its users (this
    fixture depends on make_account, so it is torn down first)."""
    started = utc_now()
    yield
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(Address).where(Address.created_at >= started))


def _error(response: Response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code


async def _create(client: AsyncClient, headers: dict[str, str], **fields: Any) -> dict[str, Any]:
    response = await client.post(URL, json=BODY | fields, headers=headers)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


async def test_create_normalizes_and_the_first_is_default(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    customer = await make_account("customer")

    first = await auth_client.post(
        URL,
        json=BODY | {"postal_code": "۱۲۳۴۵-۶۷۸۹۰", "user_id": str(uuid4()), "id": str(uuid4())},
        headers=customer.headers,
    )
    second = await _create(auth_client, customer.headers, city="Karaj")

    assert first.status_code == 201, first.text
    assert first.headers["cache-control"] == "no-store"
    body = first.json()
    assert (body["phone"], body["postal_code"], body["is_default"]) == (
        "+989121234567",
        "1234567890",
        True,
    )
    assert second["is_default"] is False
    listing = await auth_client.get(URL, headers=customer.headers)
    assert [item["id"] for item in listing.json()] == [body["id"], second["id"]]


async def test_new_default_replaces_the_old_one(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    customer = await make_account("customer")
    first = await _create(auth_client, customer.headers)
    second = await _create(auth_client, customer.headers, is_default=True)

    listing = (await auth_client.get(URL, headers=customer.headers)).json()
    assert [(item["id"], item["is_default"]) for item in listing] == [
        (second["id"], True),
        (first["id"], False),
    ]

    switched = await auth_client.patch(
        f"{URL}/{first['id']}", json={"is_default": True}, headers=customer.headers
    )
    assert switched.status_code == 200 and switched.json()["is_default"] is True
    defaults = [
        item
        for item in (await auth_client.get(URL, headers=customer.headers)).json()
        if item["is_default"]
    ]
    assert [item["id"] for item in defaults] == [first["id"]]


async def test_deleting_the_default_promotes_the_newest(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    customer = await make_account("customer")
    first = await _create(auth_client, customer.headers)
    await _create(auth_client, customer.headers)
    newest = await _create(auth_client, customer.headers)

    removed = await auth_client.delete(f"{URL}/{first['id']}", headers=customer.headers)

    assert removed.status_code == 204 and removed.headers["cache-control"] == "no-store"
    listing = (await auth_client.get(URL, headers=customer.headers)).json()
    assert listing[0]["id"] == newest["id"] and listing[0]["is_default"] is True
    _error(
        await auth_client.delete(f"{URL}/{first['id']}", headers=customer.headers), 404, "NOT_FOUND"
    )


async def test_update_changes_sent_fields_only(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    customer = await make_account("customer")
    created = await _create(auth_client, customer.headers, plaque="12")

    response = await auth_client.patch(
        f"{URL}/{created['id']}",
        json={"city": "  Shiraz ", "plaque": None},
        headers=customer.headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["city"], body["plaque"], body["province"]) == ("Shiraz", None, "Tehran")


async def test_cap_holds_under_concurrency(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    customer = await make_account("customer")
    for _ in range(MAX_ADDRESSES - 1):
        await _create(auth_client, customer.headers)

    responses = await asyncio.gather(
        *(auth_client.post(URL, json=BODY, headers=customer.headers) for _ in range(3))
    )

    assert sorted(response.status_code for response in responses) == [201, 422, 422]
    assert len((await auth_client.get(URL, headers=customer.headers)).json()) == MAX_ADDRESSES


async def test_others_addresses_are_404(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    owner, other = await make_account("customer"), await make_account("customer")
    created = await _create(auth_client, owner.headers)
    url = f"{URL}/{created['id']}"

    _error(await auth_client.get(url, headers=other.headers), 404, "NOT_FOUND")
    _error(
        await auth_client.patch(url, json={"city": "X"}, headers=other.headers), 404, "NOT_FOUND"
    )
    _error(await auth_client.delete(url, headers=other.headers), 404, "NOT_FOUND")
    assert (await auth_client.get(URL, headers=other.headers)).json() == []
    assert (await auth_client.get(url, headers=owner.headers)).status_code == 200


@pytest.mark.parametrize(
    "fields",
    [
        {"postal_code": "123456789"},
        {"postal_code": "12345678901"},
        {"postal_code": "12345abcde"},
        {"phone": "12345"},
        {"recipient_name": "   "},
        {"address_line": "x" * 501},
        {"plaque": "x" * 21},
        {"is_default": "yes"},
        {"colour": "red"},
    ],
)
async def test_invalid_bodies_are_400(
    auth_client: AsyncClient, make_account: MakeAccount, fields: dict[str, Any]
) -> None:
    customer = await make_account("customer")
    response = await auth_client.post(URL, json=BODY | fields, headers=customer.headers)
    _error(response, 400, "VALIDATION_ERROR")


async def test_invalid_updates_are_400(auth_client: AsyncClient, make_account: MakeAccount) -> None:
    customer = await make_account("customer")
    created = await _create(auth_client, customer.headers)
    url = f"{URL}/{created['id']}"
    for body in ({}, {"city": None}, {"postal_code": "1"}, {"unknown": 1}):
        _error(
            await auth_client.patch(url, json=body, headers=customer.headers),
            400,
            "VALIDATION_ERROR",
        )
    _error(
        await auth_client.get(f"{URL}/not-a-uuid", headers=customer.headers),
        400,
        "VALIDATION_ERROR",
    )
    _error(
        await auth_client.get(URL, params={"page": 1}, headers=customer.headers),
        400,
        "VALIDATION_ERROR",
    )


async def test_every_endpoint_needs_a_user(auth_client: AsyncClient) -> None:
    target = f"{URL}/{uuid4()}"
    for method, url, body in (
        ("GET", URL, None),
        ("GET", target, None),
        ("POST", URL, {"city": 1}),
        ("PATCH", target, {"city": 1}),
        ("DELETE", target, None),
    ):
        response = await auth_client.request(method, url, json=body)
        _error(response, 401, "UNAUTHORIZED")


async def test_concurrent_defaults_leave_exactly_one(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    customer = await make_account("customer")
    await _create(auth_client, customer.headers)

    responses = await asyncio.gather(
        *(
            auth_client.post(URL, json=BODY | {"is_default": True}, headers=customer.headers)
            for _ in range(3)
        )
    )

    assert [response.status_code for response in responses] == [201, 201, 201]
    listing = (await auth_client.get(URL, headers=customer.headers)).json()
    assert sum(item["is_default"] for item in listing) == 1


# --- ownership and validation gaps (ADDR-04) -----------------------------------------


async def test_a_forged_owner_is_ignored_on_update(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    owner, other = await make_account("customer"), await make_account("customer")
    created = await _create(auth_client, owner.headers)
    url = f"{URL}/{created['id']}"

    response = await auth_client.patch(
        url, json={"city": "Qom", "user_id": str(other.id)}, headers=owner.headers
    )

    assert response.status_code == 200, response.text
    assert response.json()["city"] == "Qom"
    assert (await auth_client.get(url, headers=owner.headers)).status_code == 200
    _error(await auth_client.get(url, headers=other.headers), 404, "NOT_FOUND")
    assert (await auth_client.get(URL, headers=other.headers)).json() == []


async def test_staff_roles_get_no_access_to_customer_addresses(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    customer = await make_account("customer")
    created = await _create(auth_client, customer.headers)
    url = f"{URL}/{created['id']}"
    for role in ("admin", "super_admin", "support"):
        staff = await make_account(role)
        _error(await auth_client.get(url, headers=staff.headers), 404, "NOT_FOUND")
        _error(
            await auth_client.patch(url, json={"city": "X"}, headers=staff.headers),
            404,
            "NOT_FOUND",
        )
        _error(await auth_client.delete(url, headers=staff.headers), 404, "NOT_FOUND")
    assert (await auth_client.get(url, headers=customer.headers)).json()["city"] == "Tehran"


async def test_missing_addresses_are_404(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    customer = await make_account("customer")
    url = f"{URL}/{uuid4()}"
    _error(await auth_client.get(url, headers=customer.headers), 404, "NOT_FOUND")
    _error(
        await auth_client.patch(url, json={"city": "X"}, headers=customer.headers),
        404,
        "NOT_FOUND",
    )
    _error(await auth_client.delete(url, headers=customer.headers), 404, "NOT_FOUND")


async def test_the_cap_is_a_business_rule(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    customer = await make_account("customer")
    for _ in range(MAX_ADDRESSES):
        await _create(auth_client, customer.headers)

    response = await auth_client.post(URL, json=BODY, headers=customer.headers)

    _error(response, 422, "BUSINESS_RULE_VIOLATION")
    assert response.json()["request_id"]
