"""Discount redemptions: redeem under the code lock, confirm, release (DSC-05, D31, ADR-044)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.core.errors import AppError, ErrorCode
from app.core.time import utc_now
from app.db.models import DiscountCode, DiscountRedemption, RedemptionStatus
from app.modules.discounts.redemption import ConfirmOutcome, RedemptionService, ReleaseOutcome
from app.modules.discounts.rules import CodeRules, rules_of
from app.shared.money import MAX_PRICE_TOMAN

pytestmark = pytest.mark.integration

PHONE = "+989121112233"


@pytest_asyncio.fixture
async def engine(db_engine: AsyncEngine) -> AsyncIterator[AsyncEngine]:
    """Enough connections for every concurrent redeem to run at once."""
    wide = create_async_engine(db_engine.url, pool_size=15, max_overflow=0)
    yield wide
    await wide.dispose()


@pytest_asyncio.fixture
async def codes(db_engine: AsyncEngine) -> AsyncIterator[Callable[..., Awaitable[DiscountCode]]]:
    ids: list[UUID] = []

    async def make(**values: Any) -> DiscountCode:
        base: dict[str, Any] = {
            "code": f"R{uuid4().hex[:10].upper()}",
            "type": "percent",
            "value": 1_000,
        }
        code = DiscountCode(**(base | values))
        async with AsyncSession(db_engine, expire_on_commit=False) as session, session.begin():
            session.add(code)
        ids.append(code.id)
        return code

    yield make
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            delete(DiscountRedemption).where(DiscountRedemption.discount_code_id.in_(ids))
        )
        await session.execute(delete(DiscountCode).where(DiscountCode.id.in_(ids)))


async def _redeem(
    engine: AsyncEngine,
    code: DiscountCode,
    *,
    order_id: UUID | None = None,
    phone: str = PHONE,
    amount: int = 5_000,
    subtotal: int = 50_000,
    rules: CodeRules | None = None,
) -> DiscountRedemption | AppError:
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session, session.begin():
            return await RedemptionService(session).redeem(
                code_id=code.id,
                priced_rules=rules or rules_of(code),
                order_id=order_id or uuid4(),
                user_id=None,
                phone=phone,
                amount=amount,
                subtotal=subtotal,
            )
    except AppError as error:
        return error


async def _call(engine: AsyncEngine, method: str, order_id: UUID) -> Any:
    async with AsyncSession(engine) as session, session.begin():
        return await getattr(RedemptionService(session), method)(order_id)


async def _live(engine: AsyncEngine, code: DiscountCode) -> int:
    async with AsyncSession(engine) as session:
        statement = select(func.count()).where(
            DiscountRedemption.discount_code_id == code.id,
            DiscountRedemption.status.in_(("pending", "confirmed")),
        )
        return int(await session.scalar(statement) or 0)


def _kind(result: DiscountRedemption | AppError) -> str:
    if isinstance(result, DiscountRedemption):
        return "ok"
    detail: str = result.details[0]["type"]
    return detail


async def test_total_cap_holds_under_concurrency(engine: AsyncEngine, codes: Any) -> None:
    code = await codes(usage_limit_total=3)

    results = await asyncio.gather(
        *(_redeem(engine, code, phone=f"+98912000{index:04d}") for index in range(10))
    )

    assert sorted(_kind(result) for result in results) == ["exhausted"] * 7 + ["ok"] * 3
    assert await _live(engine, code) == 3


async def test_per_mobile_cap_holds_under_concurrency(engine: AsyncEngine, codes: Any) -> None:
    code = await codes(usage_limit_per_user=1)

    results = await asyncio.gather(*(_redeem(engine, code) for _ in range(6)))

    assert sorted(_kind(result) for result in results) == ["ok"] + ["user_exhausted"] * 5


async def test_release_frees_a_slot_and_racing_release_never_overshoots(
    engine: AsyncEngine, codes: Any
) -> None:
    code = await codes(usage_limit_total=1)
    first_order = uuid4()
    assert _kind(await _redeem(engine, code, order_id=first_order)) == "ok"
    assert _kind(await _redeem(engine, code, phone="+989120000001")) == "exhausted"

    released, *others = await asyncio.gather(
        _call(engine, "release", first_order),
        *(_redeem(engine, code, phone=f"+98912999{index:04d}") for index in range(4)),
    )

    assert released is ReleaseOutcome.RELEASED
    # Some redeem may have counted before the release committed; never more than the cap.
    assert sum(_kind(result) == "ok" for result in others) <= 1
    assert await _live(engine, code) <= 1


async def test_release_frees_a_slot_for_the_next_order(engine: AsyncEngine, codes: Any) -> None:
    code = await codes(usage_limit_total=1)
    first = uuid4()
    assert _kind(await _redeem(engine, code, order_id=first)) == "ok"
    assert _kind(await _redeem(engine, code, phone="+989120000004")) == "exhausted"

    assert await _call(engine, "release", first) is ReleaseOutcome.RELEASED

    assert _kind(await _redeem(engine, code, phone="+989120000004")) == "ok"


async def test_release_never_predates_the_payment(engine: AsyncEngine, codes: Any) -> None:
    code = await codes()
    order_id = uuid4()
    await _redeem(engine, code, order_id=order_id)
    assert await _call(engine, "confirm", order_id) is ConfirmOutcome.CONFIRMED
    async with AsyncSession(engine) as session, session.begin():
        stored = (
            await session.scalars(
                select(DiscountRedemption).where(DiscountRedemption.order_id == order_id)
            )
        ).one()
        confirmed_at = stored.confirmed_at
        assert confirmed_at is not None
        outcome = await RedemptionService(session).release(
            order_id, now=confirmed_at - timedelta(seconds=1)
        )
        released_at = stored.released_at

    assert outcome is ReleaseOutcome.RELEASED
    assert released_at == confirmed_at


async def test_redeem_is_idempotent_per_order_and_one_per_order(
    engine: AsyncEngine, codes: Any
) -> None:
    code, other = await codes(), await codes()
    order_id = uuid4()
    first = await _redeem(engine, code, order_id=order_id)
    again = await _redeem(engine, code, order_id=order_id)

    assert isinstance(first, DiscountRedemption) and isinstance(again, DiscountRedemption)
    assert again.id == first.id
    for changed in (
        {"amount": 4_000},
        {"phone": "+989120000002"},
    ):
        result = await _redeem(engine, code, order_id=order_id, **changed)
        assert isinstance(result, AppError) and result.status_code == 409
    other_code = await _redeem(engine, other, order_id=order_id)
    assert isinstance(other_code, AppError) and other_code.status_code == 409
    # Released orders do not redeem again (orders are immutable).
    assert await _call(engine, "release", order_id) is ReleaseOutcome.RELEASED
    after = await _redeem(engine, code, order_id=order_id)
    assert isinstance(after, AppError) and after.details[0]["type"] == "order_already_redeemed"


async def test_rules_changed_since_pricing_is_409(
    engine: AsyncEngine, codes: Any, db_engine: AsyncEngine
) -> None:
    code = await codes(value=1_000)
    priced = rules_of(code)
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            update(DiscountCode).where(DiscountCode.id == code.id).values(value=2_000)
        )

    result = await _redeem(engine, code, rules=priced)

    assert isinstance(result, AppError)
    assert (result.status_code, result.code) == (409, ErrorCode.PRICE_CHANGED)


@pytest.mark.parametrize("change", [{"is_active": False}, {"deleted_at": "now"}])
async def test_deactivated_or_deleted_code_is_invalid(
    engine: AsyncEngine, codes: Any, db_engine: AsyncEngine, change: dict[str, Any]
) -> None:
    code = await codes()
    pending_order = uuid4()
    assert _kind(await _redeem(engine, code, order_id=pending_order)) == "ok"
    values = {key: utc_now() if value == "now" else value for key, value in change.items()}
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            update(DiscountCode).where(DiscountCode.id == code.id).values(**values)
        )

    async with AsyncSession(db_engine) as session:
        fresh = await session.get(DiscountCode, code.id)
    assert fresh is not None
    # Priced with the current rules, so the rejection is the code itself, not a change.
    result = await _redeem(engine, code, rules=rules_of(fresh), phone="+989120000003")

    assert isinstance(result, AppError)
    assert (result.code, result.details[0]["type"]) == (
        ErrorCode.DISCOUNT_NOT_APPLICABLE,
        "invalid",
    )
    # An order that already redeemed keeps its use; payment still confirms it.
    assert await _call(engine, "confirm", pending_order) is ConfirmOutcome.CONFIRMED


async def _waiting_on_locks(engine: AsyncEngine, count: int) -> None:
    """Wait (bounded) until ``count`` backends wait for a lock: the redeems are queued."""
    for _ in range(200):
        async with engine.connect() as connection:
            waiting = await connection.scalar(
                text("SELECT count(*) FROM pg_locks WHERE NOT granted")
            )
        if (waiting or 0) >= count:
            return
        await asyncio.sleep(0.05)
    raise AssertionError("the redeems never queued on the code lock")


async def test_redeems_queued_behind_a_deactivation_never_redeem(
    engine: AsyncEngine, codes: Any
) -> None:
    code = await codes()
    async with AsyncSession(engine) as session, session.begin():
        locked = await RedemptionService(session).lock_code(code.id)
        assert locked is not None
        queued = [
            asyncio.create_task(_redeem(engine, code, phone=f"+98912777{index:04d}"))
            for index in range(3)
        ]
        await _waiting_on_locks(engine, 3)
        locked.is_active = False

    results = await asyncio.gather(*queued)

    # Each queued redeem sees the deactivated rules once it gets the lock.
    assert [_kind(result) for result in results] == ["code_changed"] * 3
    assert await _live(engine, code) == 0


async def test_confirm_and_release_outcomes(engine: AsyncEngine, codes: Any) -> None:
    code = await codes()
    paid, cancelled, plain = uuid4(), uuid4(), uuid4()
    for order_id in (paid, cancelled):
        await _redeem(engine, code, order_id=order_id, phone=f"+98912{order_id.int % 10**7:07d}")

    assert await _call(engine, "confirm", paid) is ConfirmOutcome.CONFIRMED
    assert await _call(engine, "confirm", paid) is ConfirmOutcome.ALREADY_CONFIRMED
    assert await _call(engine, "release", cancelled) is ReleaseOutcome.RELEASED
    assert await _call(engine, "release", cancelled) is ReleaseOutcome.ALREADY_RELEASED
    # Paid after expiry (D32): the caller releases; confirm never raises.
    assert await _call(engine, "confirm", cancelled) is ConfirmOutcome.RELEASED
    # A refund releases a confirmed use, keeping confirmed_at.
    assert await _call(engine, "release", paid) is ReleaseOutcome.RELEASED
    assert await _call(engine, "confirm", plain) is ConfirmOutcome.NONE
    assert await _call(engine, "release", plain) is ReleaseOutcome.NONE
    async with AsyncSession(engine) as session:
        refunded = (
            await session.scalars(
                select(DiscountRedemption).where(DiscountRedemption.order_id == paid)
            )
        ).one()
    assert refunded.status == RedemptionStatus.RELEASED and refunded.confirmed_at is not None


async def test_inputs_are_checked(engine: AsyncEngine, codes: Any) -> None:
    code = await codes()
    for fields, error in (
        ({"amount": 6_000, "subtotal": 5_000}, ValueError),
        ({"amount": -1}, ValueError),
        ({"amount": MAX_PRICE_TOMAN + 1, "subtotal": MAX_PRICE_TOMAN + 1}, ValueError),
        ({"amount": True}, TypeError),
        ({"amount": 1.5}, TypeError),
        ({"phone": "09121112233"}, ValueError),
    ):
        with pytest.raises(error):
            await _redeem(engine, code, **fields)


async def test_methods_need_the_callers_transaction(engine: AsyncEngine, codes: Any) -> None:
    code = await codes()
    async with AsyncSession(engine) as session:
        service = RedemptionService(session)
        with pytest.raises(RuntimeError):
            await service.redeem(
                code_id=code.id,
                priced_rules=rules_of(code),
                order_id=uuid4(),
                user_id=None,
                phone=PHONE,
                amount=1,
                subtotal=1,
            )
        with pytest.raises(RuntimeError):
            await service.confirm(uuid4())
        with pytest.raises(RuntimeError):
            await service.release(uuid4())
