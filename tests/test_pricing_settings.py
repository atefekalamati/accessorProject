from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from conftest import MakeAccount
from httpx import AsyncClient, Response
from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import AuditLog, PricingSetting
from app.modules.pricing.repository import to_policy
from app.shared.money import RoundingMode

URL = "/api/v1/admin/pricing/settings"
_COLUMNS = (
    "id",
    "singleton",
    "currency",
    "tax_enabled",
    "default_tax_rate_bps",
    "rounding_mode",
    "rounding_step",
    "version",
    "updated_by",
    "updated_at",
)


def _error(response: Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body: dict[str, Any] = response.json()["error"]
    assert body["code"] == code
    return body


@pytest_asyncio.fixture
async def restore_settings(db_engine: AsyncEngine) -> AsyncIterator[dict[str, Any]]:
    """The settings row is global: put it back exactly as it was after each test."""
    async with AsyncSession(db_engine) as session:
        row = (await session.execute(select(PricingSetting.__table__))).mappings().one()
    original = {column: row[column] for column in _COLUMNS}
    yield original
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(PricingSetting))
        await session.execute(insert(PricingSetting).values(**original))


async def _audits(db_engine: AsyncEngine, setting_id: Any, actor_id: Any) -> list[AuditLog]:
    """Audit rows of this test's actor (rows of earlier tests cannot be deleted)."""
    async with AsyncSession(db_engine) as session:
        statement = (
            select(AuditLog)
            .where(
                AuditLog.entity_id == setting_id,
                AuditLog.action == "pricing.settings_updated",
                AuditLog.actor_user_id == actor_id,
            )
            .order_by(AuditLog.created_at)
        )
        return list((await session.scalars(statement)).all())


def test_policy_from_row_uses_a_real_rounding_mode() -> None:
    row = PricingSetting(
        tax_enabled=True,
        default_tax_rate_bps=900,
        rounding_mode="up",
        rounding_step=1000,
        version=7,
    )

    policy = to_policy(row)

    assert policy.rounding_mode is RoundingMode.UP
    assert (policy.tax_enabled, policy.tax_rate_bps, policy.rounding_step, policy.version) == (
        True,
        900,
        1000,
        7,
    )


# --- access --------------------------------------------------------------------------


@pytest.mark.integration
async def test_settings_need_authentication_before_validation(auth_client: AsyncClient) -> None:
    _error(await auth_client.get(URL), 401, "UNAUTHORIZED")
    _error(await auth_client.patch(URL, json={"rounding_step": "x", "bad": 1}), 401, "UNAUTHORIZED")


@pytest.mark.integration
@pytest.mark.parametrize("role", ["admin", "content_manager", "support", "customer"])
async def test_only_super_admin_reads_or_changes_settings(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    restore_settings: dict[str, Any],
    role: str,
) -> None:
    actor = await make_account(role)

    _error(await auth_client.get(URL, headers=actor.headers), 403, "FORBIDDEN")
    # Authorization comes before validation: an invalid body is still a 403.
    for body in ({"rounding_step": 10}, {"rounding_step": "x", "bad": 1}):
        response = await auth_client.patch(URL, json=body, headers=actor.headers)
        _error(response, 403, "FORBIDDEN")


# --- read ----------------------------------------------------------------------------


@pytest.mark.integration
async def test_get_settings(
    auth_client: AsyncClient, make_account: MakeAccount, restore_settings: dict[str, Any]
) -> None:
    actor = await make_account("super_admin")

    response = await auth_client.get(URL, headers=actor.headers)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert set(body) == {
        "currency",
        "tax_enabled",
        "default_tax_rate_bps",
        "rounding_mode",
        "rounding_step",
        "version",
        "updated_by",
        "updated_at",
    }
    assert body["currency"] == "TOMAN"
    assert body["version"] == restore_settings["version"]
    assert (await auth_client.get(URL, params={"x": 1}, headers=actor.headers)).status_code == 400


@pytest.mark.integration
async def test_missing_settings_row_is_404(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    restore_settings: dict[str, Any],
    db_engine: AsyncEngine,
) -> None:
    actor = await make_account("super_admin")
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(PricingSetting))

    _error(await auth_client.get(URL, headers=actor.headers), 404, "NOT_FOUND")
    response = await auth_client.patch(URL, json={"rounding_step": 10}, headers=actor.headers)
    _error(response, 404, "NOT_FOUND")


# --- update --------------------------------------------------------------------------


@pytest.mark.integration
async def test_update_bumps_version_and_audits(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    restore_settings: dict[str, Any],
    db_engine: AsyncEngine,
) -> None:
    actor = await make_account("super_admin")
    version = restore_settings["version"]

    response = await auth_client.patch(
        URL,
        json={
            "tax_enabled": True,
            "default_tax_rate_bps": 0,  # a zero rate is allowed (ADR-033)
            "rounding_mode": "down",
            "rounding_step": 1000,
            # System fields are ignored, never applied.
            "currency": "IRR",
            "version": 999,
            "updated_by": None,
        },
        headers=actor.headers,
    )

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["tax_enabled"] is True
    assert (body["default_tax_rate_bps"], body["rounding_mode"], body["rounding_step"]) == (
        0,
        "down",
        1000,
    )
    assert (body["currency"], body["version"]) == ("TOMAN", version + 1)
    assert body["updated_by"] == str(actor.id)
    [audit] = await _audits(db_engine, restore_settings["id"], actor.id)
    assert audit.actor_user_id == actor.id
    diff = audit.metadata_["diff"]
    assert (diff["version"]["before"], diff["version"]["after"]) == (version, version + 1)
    assert (diff["rounding_step"]["before"], diff["rounding_step"]["after"]) == (
        restore_settings["rounding_step"],
        1000,
    )


@pytest.mark.integration
async def test_unchanged_body_is_not_audited_or_bumped(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    restore_settings: dict[str, Any],
    db_engine: AsyncEngine,
) -> None:
    actor = await make_account("super_admin")
    same = {"rounding_step": restore_settings["rounding_step"]}

    response = await auth_client.patch(URL, json=same, headers=actor.headers)

    assert response.status_code == 200
    assert response.json()["version"] == restore_settings["version"]
    assert await _audits(db_engine, restore_settings["id"], actor.id) == []


@pytest.mark.integration
@pytest.mark.parametrize(
    "body",
    [
        {},
        {"currency": "TOMAN", "version": 3},  # empty once system fields are dropped
        {"unknown": 1},
        {"rounding_step": None},
        {"tax_enabled": None},
        {"rounding_step": 0},
        {"rounding_step": 1_000_001},
        {"rounding_step": 10.0},
        {"rounding_step": "10"},
        {"default_tax_rate_bps": -1},
        {"default_tax_rate_bps": 10_001},
        {"default_tax_rate_bps": 9.5},
        {"default_tax_rate_bps": True},
        {"tax_enabled": "true"},
        {"tax_enabled": 1},
        {"rounding_mode": "banker"},
    ],
)
async def test_invalid_body_is_400(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    restore_settings: dict[str, Any],
    body: dict[str, Any],
) -> None:
    actor = await make_account("super_admin")

    response = await auth_client.patch(URL, json=body, headers=actor.headers)

    _error(response, 400, "VALIDATION_ERROR")


@pytest.mark.integration
async def test_concurrent_updates_are_serialized(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    restore_settings: dict[str, Any],
    db_engine: AsyncEngine,
) -> None:
    actor = await make_account("super_admin")
    version = restore_settings["version"]
    bodies = [{"rounding_step": 10}, {"rounding_step": 100}]

    responses = await asyncio.gather(
        *(auth_client.patch(URL, json=body, headers=actor.headers) for body in bodies)
    )

    assert [response.status_code for response in responses] == [200, 200]
    # Both changes landed one after the other: no lost update, two versions, two audits.
    assert sorted(response.json()["version"] for response in responses) == [
        version + 1,
        version + 2,
    ]
    audits = await _audits(db_engine, restore_settings["id"], actor.id)
    assert len(audits) == 2
    async with AsyncSession(db_engine) as session:
        final = (await session.scalars(select(PricingSetting))).one()
    assert final.version == version + 2
    assert final.rounding_step in (10, 100)
    last = max(responses, key=lambda response: response.json()["version"])
    assert final.rounding_step == last.json()["rounding_step"]
    # The second change saw the first one's result as its "before". created_at can tie on
    # Windows' coarse clock, so compare the version pairs, not the row order.
    pairs = {
        (audit.metadata_["diff"]["version"]["before"], audit.metadata_["diff"]["version"]["after"])
        for audit in audits
    }
    assert pairs == {(version, version + 1), (version + 1, version + 2)}


@pytest.mark.integration
async def test_external_change_makes_the_same_patch_a_noop(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    restore_settings: dict[str, Any],
    db_engine: AsyncEngine,
) -> None:
    """The service compares against the row as it is now, not as it was earlier."""
    actor = await make_account("super_admin")
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(update(PricingSetting).values(rounding_step=50))

    response = await auth_client.patch(URL, json={"rounding_step": 50}, headers=actor.headers)

    assert response.status_code == 200
    assert response.json()["version"] == restore_settings["version"]  # unchanged: no bump
