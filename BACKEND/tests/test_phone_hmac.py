"""Redemption phone digests and key rotation (DSC-06, ADR-063 A2)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from alembic.config import Config
from conftest import new_order
from pydantic import ValidationError
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from alembic import command
from app.core.config import Environment, Settings, get_settings
from app.core.phone_hmac import PhoneKey, parse_phone_keys
from app.db.models import DiscountCode, DiscountRedemption
from app.modules.discounts.repository import DiscountRepository

PHONE = "+989121112233"
PRE_HASH_REVISION = "20261113_0034"
A = "a" * 32
B = "b" * 32

# --- pure ----------------------------------------------------------------------------


def test_parse_keys_newest_first() -> None:
    keys = parse_phone_keys(f" k2:{A} , k1:{B}")
    assert [key.key_id for key in keys.keys] == ["k2", "k1"]
    assert keys.write.key_id == "k2"
    assert keys.get("k1") == PhoneKey("k1", B.encode())
    assert keys.get("k9") is None


@pytest.mark.parametrize(
    "value",
    [
        "",
        "k1",
        f"K1:{A}",
        f"k1:{'x' * 31}",
        f"k1:{A},k1:{B}",
        f"a-very-long-key-id-17:{A}",
        f":{A}",
    ],
)
def test_parse_keys_rejects_bad_values(value: str) -> None:
    with pytest.raises(ValueError):
        parse_phone_keys(value)


def test_the_secret_is_never_in_a_repr() -> None:
    keys = parse_phone_keys(f"k2:{A},k1:{B}")
    assert A not in repr(keys) and B not in repr(keys) and "k2" in repr(keys)


def test_digest_is_keyed_and_stable() -> None:
    one, two = PhoneKey("k1", A.encode()), PhoneKey("k2", B.encode())
    assert one.digest(PHONE) == one.digest(PHONE)
    assert len(one.digest(PHONE)) == 64 and PHONE not in one.digest(PHONE)
    assert one.digest(PHONE) != two.digest(PHONE)
    assert one.digest(PHONE) != one.digest("+989121112234")
    keys = parse_phone_keys(f"k2:{B},k1:{A}")
    assert keys.digests(PHONE) == [("k2", two.digest(PHONE)), ("k1", one.digest(PHONE))]


def test_settings_validate_and_require_keys_in_production(settings: Settings) -> None:
    with pytest.raises(ValidationError):
        settings.model_validate(settings.model_dump() | {"phone_hmac_keys": "bad"})
    unset = settings.model_copy(update={"phone_hmac_keys": None})
    with pytest.raises(RuntimeError, match="PHONE_HMAC_KEYS"):
        unset.phone_keys()
    production: dict[str, Any] = {
        "environment": Environment.PRODUCTION,
        "cors_origins": ["https://shop.example"],
        "otp_mock_enabled": False,
        "phone_hmac_keys": None,
    }
    with pytest.raises(ValidationError, match="PHONE_HMAC_KEYS is required"):
        Settings.model_validate(
            {k: v for k, v in settings.model_dump().items() if v is not None} | production
        )


# --- database --------------------------------------------------------------------------


@pytest_asyncio.fixture
async def code(db_engine: AsyncEngine) -> AsyncIterator[DiscountCode]:
    found = DiscountCode(code=f"H{uuid4().hex[:10].upper()}", type="fixed", value=1_000)
    async with AsyncSession(db_engine, expire_on_commit=False) as session, session.begin():
        session.add(found)
    yield found
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            delete(DiscountRedemption).where(DiscountRedemption.discount_code_id == found.id)
        )
        await session.execute(delete(DiscountCode).where(DiscountCode.id == found.id))


async def _insert(engine: AsyncEngine, code: DiscountCode, key: PhoneKey, **values: Any) -> None:
    async with AsyncSession(engine) as session, session.begin():
        session.add(
            DiscountRedemption(
                discount_code_id=code.id,
                order_id=await new_order(),
                phone_hmac=key.digest(values.pop("phone", PHONE)),
                phone_key_id=key.key_id,
                code=code.code,
                amount=1,
                **values,
            )
        )


@pytest.mark.integration
@pytest.mark.usefixtures("order_factory")
async def test_usage_counts_uses_under_every_key(
    db_engine: AsyncEngine, code: DiscountCode
) -> None:
    keys = get_settings().phone_keys()
    assert len(keys.keys) >= 2  # conftest: a write key and an older one
    await _insert(db_engine, code, keys.write)
    await _insert(db_engine, code, keys.keys[-1])  # recorded before a rotation
    await _insert(db_engine, code, keys.write, phone="+989121112234")  # someone else
    unknown = PhoneKey("gone", b"z" * 32)
    await _insert(db_engine, code, unknown)  # a key that was removed no longer counts

    async with AsyncSession(db_engine) as session:
        usage = await DiscountRepository(session).usage(code.id, PHONE)
        guest = await DiscountRepository(session).usage(code.id, None)

    assert (usage.total_live, usage.user_live) == (4, 2)
    assert (guest.total_live, guest.user_live) == (4, None)


@pytest.mark.integration
async def test_no_raw_phone_column_remains(db_engine: AsyncEngine) -> None:
    async with AsyncSession(db_engine) as session:
        columns = set(
            await session.scalars(
                text(
                    "SELECT column_name FROM information_schema.columns"
                    " WHERE table_name = 'discount_redemptions'"
                )
            )
        )
    assert {"phone_hmac", "phone_key_id"} <= columns
    assert "phone" not in columns


async def _alembic(database_url: str, action: str, revision: str) -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    await asyncio.to_thread(getattr(command, action), config, revision)


@pytest.mark.integration
@pytest.mark.usefixtures("order_factory")
async def test_migration_backfills_digests_and_downgrade_restores_phones(
    db_engine: AsyncEngine, migrated_database: str, code: DiscountCode
) -> None:
    order_id: UUID = await new_order()
    async with AsyncSession(db_engine) as session:
        order_phone = await session.scalar(
            text("SELECT phone FROM orders WHERE id = :id"), {"id": order_id}
        )
    redemption_id = uuid4()
    run: Callable[[str, str], Awaitable[None]] = lambda action, rev: _alembic(  # noqa: E731
        migrated_database, action, rev
    )
    try:
        await run("downgrade", PRE_HASH_REVISION)
        async with AsyncSession(db_engine) as session, session.begin():
            await session.execute(
                text(
                    "INSERT INTO discount_redemptions"
                    " (id, discount_code_id, order_id, phone, code, amount)"
                    " VALUES (:id, :code_id, :order_id, :phone, :code, 1)"
                ),
                {
                    "id": redemption_id,
                    "code_id": code.id,
                    "order_id": order_id,
                    "phone": PHONE,
                    "code": code.code,
                },
            )

        await run("upgrade", "head")
        async with AsyncSession(db_engine) as session:
            row = (
                await session.execute(
                    select(DiscountRedemption.phone_hmac, DiscountRedemption.phone_key_id).where(
                        DiscountRedemption.id == redemption_id
                    )
                )
            ).one()
        write = get_settings().phone_keys().write
        assert (row.phone_hmac, row.phone_key_id) == (write.digest(PHONE), write.key_id)

        await run("downgrade", PRE_HASH_REVISION)
        async with AsyncSession(db_engine) as session:
            restored = await session.scalar(
                text("SELECT phone FROM discount_redemptions WHERE id = :id"),
                {"id": redemption_id},
            )
        assert restored == order_phone  # from the order snapshot
    finally:
        await run("upgrade", "head")
