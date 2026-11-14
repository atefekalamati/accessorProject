from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, event, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

# app.main intentionally validates required settings at import time. Tests supply
# isolated startup values before importing the application factory.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://user:password@localhost:5432/project_ak"
)
os.environ.setdefault("JWT_SECRET", "test-secret-that-is-at-least-32-characters")
os.environ.setdefault("OTP_HASH_SECRET", "test-otp-hash-secret-at-least-32-characters")

from alembic import command
from app.core.config import Environment, MediaStorage, Settings
from app.core.time import utc_now
from app.db.models import (
    CartItem,
    Category,
    CategoryFilter,
    DiscountRedemption,
    InventoryItem,
    InventoryMovement,
    InventoryReservation,
    InventoryReservationItem,
    Media,
    Order,
    OrderAddress,
    OrderItem,
    OrderPriceSnapshot,
    OrderStatusHistory,
    OtpCode,
    Payment,
    PriceHistory,
    Product,
    ProductAttribute,
    ProductMedia,
    ProductStatus,
    ProductVariant,
    ReturnRequest,
    Shipment,
    ShippingMethod,
    User,
    UserRole,
    VariantOption,
)
from app.db.models.inventory import DEFAULT_WAREHOUSE_ID
from app.db.models.orders import format_order_number, order_number_seq
from app.db.seed import role_id, seed_rbac
from app.main import create_app
from app.modules.auth.otp import hash_otp_code, otp_hash_key

TEST_DATABASE_SUFFIX = "_test"
TEST_DATABASE_GUARD_EXIT_CODE = 3


def unsafe_test_database_reason(value: str | None) -> str | None:
    """Return why TEST_DATABASE_URL is unsafe, or None when it is unset or safe.

    Integration tests downgrade the whole schema, so only a database whose name
    ends with ``_test`` is accepted.
    """
    if not value:
        return None
    try:
        database_name = make_url(value).database
    except ArgumentError:
        return "TEST_DATABASE_URL is not a valid database URL"
    if database_name is None or not database_name.endswith(TEST_DATABASE_SUFFIX):
        return (
            f"TEST_DATABASE_URL must point to a database whose name ends with "
            f"'{TEST_DATABASE_SUFFIX}' (got {database_name!r})"
        )
    return None


def pytest_sessionstart(session: pytest.Session) -> None:
    error = unsafe_test_database_reason(os.getenv("TEST_DATABASE_URL"))
    if error is not None:
        pytest.exit(f"Aborting test session: {error}", returncode=TEST_DATABASE_GUARD_EXIT_CODE)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://user:password@localhost:5432/project_ak",
        jwt_secret="test-secret-that-is-at-least-32-characters",
        environment=Environment.TESTING,
        cors_origins=["http://localhost:3000"],
        otp_mock_enabled=True,
        otp_hash_secret="test-otp-hash-secret-at-least-32-characters",
        media_storage=MediaStorage.MEMORY,
        media_public_base_url="https://cdn.example.com/media",
        media_allowed_hosts=["cdn.example.com"],
        # Tests sweep explicitly (tests/test_reservation_jobs.py).
        reservation_sweep_seconds=0,
        # Tests reconcile explicitly (tests/test_payment_reconcile.py).
        payment_reconcile_seconds=0,
        # Every test client shares one IP; tests/test_rate_limit.py sets small caps.
        rate_limit_per_ip=1_000_000,
        rate_limit_admin_per_user=1_000_000,
    )


@pytest_asyncio.fixture
async def client(settings: Settings) -> AsyncIterator[AsyncClient]:
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
            yield test_client


def worker_database_url(value: str, worker_id: str) -> str:
    """The database of one pytest-xdist worker: ``<base>_test`` -> ``<base>_<worker>_test``.

    Without xdist (``worker_id == "master"``) the URL is returned unchanged.
    """
    if worker_id == "master":
        return value
    url = make_url(value)
    base = (url.database or "").removesuffix(TEST_DATABASE_SUFFIX)
    worker_url = url.set(database=f"{base}_{worker_id}{TEST_DATABASE_SUFFIX}")
    return worker_url.render_as_string(hide_password=False)


async def _prepare_worker_database(admin_url: str, database_url: str) -> None:
    """Create the worker database when missing; ``admin_url`` is the validated base database."""
    name = make_url(database_url).database
    assert name is not None and unsafe_test_database_reason(database_url) is None
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            quoted = connection.dialect.identifier_preparer.quote(name)
            exists = await connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}
            )
            if not exists:
                # template0 accepts no connections, so parallel workers cannot block each other.
                await connection.execute(text(f"CREATE DATABASE {quoted} TEMPLATE template0"))
            # A disposable database needs no durable commits (no WAL flush per commit).
            await connection.execute(text(f"ALTER DATABASE {quoted} SET synchronous_commit = off"))
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def database_url(worker_id: str) -> str:
    value = os.getenv("TEST_DATABASE_URL")
    if not value:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    # The database name itself is validated once per session in conftest.pytest_sessionstart.
    worker_url = worker_database_url(value, worker_id)
    if worker_url != value:
        asyncio.run(_prepare_worker_database(value, worker_url))
    return worker_url


@pytest.fixture(scope="session")
def migrated_database(database_url: str) -> Iterator[str]:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

    command.downgrade(config, "base")
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    yield database_url


@pytest_asyncio.fixture
async def db_engine(migrated_database: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(
        migrated_database,
        connect_args={"server_settings": {"timezone": "UTC"}},
    )
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        yield session
        await session.rollback()


AUTH_CLIENT_IP = "198.51.100.23"
TEST_OTP_CODE = "123456"


@pytest_asyncio.fixture
async def auth_client(settings: Settings, db_engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    """A client on the migrated test database, with RBAC roles seeded."""
    async with AsyncSession(db_engine) as session, session.begin():
        await seed_rbac(session)
    database_url = db_engine.url.render_as_string(hide_password=False)
    application = create_app(settings.model_copy(update={"database_url": database_url}))
    async with application.router.lifespan_context(application):
        transport = ASGITransport(app=application, client=(AUTH_CLIENT_IP, 50000))
        async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
            yield test_client


@pytest.fixture
def issue_otp(settings: Settings, db_engine: AsyncEngine) -> Callable[..., Awaitable[OtpCode]]:
    """Insert an OTP for ``mobile`` directly, bypassing request-otp rate limits."""

    async def _issue(
        mobile: str, code: str = TEST_OTP_CODE, *, ttl: timedelta = timedelta(minutes=2)
    ) -> OtpCode:
        now = utc_now()
        otp = OtpCode(
            mobile=mobile,
            code_hash=hash_otp_code(code, mobile, otp_hash_key(settings)),
            expires_at=now + ttl,
            created_at=now,
        )
        async with AsyncSession(db_engine, expire_on_commit=False) as session, session.begin():
            session.add(otp)
        return otp

    return _issue


MEDIA_BASE_URL = "https://cdn.example.com/media"
MakeMedia = Callable[[], Awaitable[Media]]


@pytest_asyncio.fixture
async def make_media(db_engine: AsyncEngine) -> AsyncIterator[MakeMedia]:
    """Insert media rows (no file); their public URL is MEDIA_BASE_URL/<storage_key>."""
    created: list[Media] = []

    async def _make() -> Media:
        media = Media(
            storage_key=f"{uuid4().hex}.webp",
            content_type="image/webp",
            size_bytes=1000,
            width=10,
            height=10,
        )
        async with AsyncSession(db_engine, expire_on_commit=False) as session, session.begin():
            session.add(media)
        created.append(media)
        return media

    yield _make
    ids = [media.id for media in created]
    async with AsyncSession(db_engine) as session, session.begin():
        # Categories of the test may still point at the media (FK RESTRICT).
        await session.execute(
            update(Category).where(Category.image_media_id.in_(ids)).values(image_media_id=None)
        )
        await session.execute(delete(Media).where(Media.id.in_(ids)))


def unique_mobile() -> str:
    return f"+989{uuid4().int % 1_000_000_000:09d}"


@pytest.fixture
def new_mobile() -> str:
    return unique_mobile()


# --- staff accounts (CAT-11, CAT-12) ---------------------------------------------


@dataclass(frozen=True, slots=True)
class Account:
    id: UUID
    headers: dict[str, str]


MakeAccount = Callable[..., Awaitable[Account]]


@pytest_asyncio.fixture
async def make_account(
    auth_client: AsyncClient,
    issue_otp: Callable[..., Awaitable[OtpCode]],
    db_engine: AsyncEngine,
) -> AsyncIterator[MakeAccount]:
    mobiles: list[str] = []

    async def _make(*roles: str) -> Account:
        mobile = f"+989{uuid4().int % 1_000_000_000:09d}"
        mobiles.append(mobile)
        await issue_otp(mobile)
        response = await auth_client.post(
            "/api/v1/auth/verify-otp", json={"mobile": mobile, "code": "123456"}
        )
        assert response.status_code == 200
        async with AsyncSession(db_engine) as session, session.begin():
            user_id: UUID = (
                await session.scalars(select(User.id).where(User.phone == mobile))
            ).one()
            await session.execute(delete(UserRole).where(UserRole.user_id == user_id))
            session.add_all(UserRole(user_id=user_id, role_id=role_id(name)) for name in roles)
        return Account(
            id=user_id, headers={"Authorization": f"Bearer {response.json()['access_token']}"}
        )

    yield _make
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(User).where(User.phone.in_(mobiles)))


# --- orders (ORD-01) ---------------------------------------------------------------


MakeOrder = Callable[..., Awaitable[UUID]]


async def insert_order(
    session: AsyncSession, user_id: UUID, method_id: UUID, **values: Any
) -> Order:
    """A minimal, valid order header (no lines) for tests that only need an order id."""
    now = utc_now()
    number = int(await session.scalar(order_number_seq.next_value()) or 0)
    order = Order(
        order_number=format_order_number(now.year, number),
        user_id=user_id,
        phone="+989120000000",
        subtotal=0,
        product_discount_total=0,
        discount_code_amount=0,
        tax_amount=0,
        shipping_amount=0,
        grand_total=0,
        shipping_method_id=method_id,
        shipping_method_title="Test post",
        created_at=now,
        updated_at=now,
    )
    for name, value in values.items():
        setattr(order, name, value)
    session.add(order)
    await session.flush()
    return order


async def delete_orders(session: AsyncSession, order_ids: list[UUID]) -> None:
    """Remove orders and everything that references them (RESTRICT everywhere)."""
    if not order_ids:
        return
    # Items and history go with their request (CASCADE).
    await session.execute(delete(ReturnRequest).where(ReturnRequest.order_id.in_(order_ids)))
    await session.execute(delete(Payment).where(Payment.order_id.in_(order_ids)))
    reservations = select(InventoryReservation.id).where(
        InventoryReservation.order_id.in_(order_ids)
    )
    await session.execute(
        delete(InventoryReservationItem).where(
            InventoryReservationItem.reservation_id.in_(reservations)
        )
    )
    await session.execute(
        delete(InventoryReservation).where(InventoryReservation.order_id.in_(order_ids))
    )
    await session.execute(
        delete(DiscountRedemption).where(DiscountRedemption.order_id.in_(order_ids))
    )
    for model in (OrderStatusHistory, OrderItem, OrderPriceSnapshot, OrderAddress, Shipment):
        await session.execute(delete(model).where(model.order_id.in_(order_ids)))
    await session.execute(delete(Order).where(Order.id.in_(order_ids)))


@pytest_asyncio.fixture
async def make_order(db_engine: AsyncEngine) -> AsyncIterator[MakeOrder]:
    """Create minimal orders owned by a throwaway user; torn down with all their references.

    It removes the reservations and redemptions of its orders itself, so those never block
    teardown. Order lines (variants) and a ``discount_code_id`` (codes) are RESTRICT: request
    ``catalog`` and code fixtures before this one so it is torn down first (LIFO).
    """
    async with AsyncSession(db_engine, expire_on_commit=False) as session, session.begin():
        user = User(phone=f"+989{uuid4().int % 1_000_000_000:09d}")
        method = ShippingMethod(title=f"Test post {uuid4().hex[:6]}", cost=0)
        session.add_all([user, method])
    order_ids: list[UUID] = []

    async def _make(**values: Any) -> UUID:
        async with AsyncSession(db_engine) as session, session.begin():
            order = await insert_order(session, user.id, method.id, **values)
            order_ids.append(order.id)
            return order.id

    yield _make
    async with AsyncSession(db_engine) as session, session.begin():
        await delete_orders(session, order_ids)
        await session.execute(delete(ShippingMethod).where(ShippingMethod.id == method.id))
        await session.execute(delete(User).where(User.id == user.id))


_ORDER_FACTORIES: list[MakeOrder] = []


@pytest_asyncio.fixture
async def order_factory(make_order: MakeOrder) -> AsyncIterator[None]:
    """Lets module helpers call ``new_order()``; use with ``pytest.mark.usefixtures``."""
    _ORDER_FACTORIES.append(make_order)
    yield
    _ORDER_FACTORIES.pop()


async def new_order(**values: Any) -> UUID:
    """A real order id (reservations and redemptions reference orders since ORD-01)."""
    return await _ORDER_FACTORIES[-1](**values)


# --- catalog builder (CAT-07, CAT-08, CAT-12) -------------------------------------

INTERNAL_FIELDS = {
    "created_by",
    "updated_by",
    "deleted_at",
    "low_stock_threshold",
    "total",
    "reserved",
    "free",
    "total_quantity",
    "reserved_quantity",
    "price_version",
    "tax_enabled",
    "is_active",
    "is_purchasable",
    "status",
}


def unique_slug(prefix: str = "prd") -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


@dataclass
class Catalog:
    """Builds catalog rows directly in the database and removes them afterwards."""

    engine: AsyncEngine
    make_media: MakeMedia
    categories: list[UUID] = field(default_factory=list)

    async def category(self, *, parent: UUID | None = None, active: bool = True) -> Category:
        category = Category(
            title="Rings", slug=unique_slug("cat"), parent_id=parent, is_active=active
        )
        async with AsyncSession(self.engine, expire_on_commit=False) as session, session.begin():
            session.add(category)
        self.categories.append(category.id)
        return category

    async def product(
        self,
        *,
        category: UUID | None = None,
        status: str = ProductStatus.PUBLISHED,
        title: str = "Silver ring",
        published_at: datetime | None = None,
        attributes: dict[str, str] | None = None,
    ) -> Product:
        category = category or (await self.category()).id
        if status == ProductStatus.PUBLISHED and published_at is None:
            published_at = utc_now()
        product = Product(
            category_id=category,
            title=title,
            slug=unique_slug(),
            description="Handmade",
            status=status,
            published_at=published_at,
        )
        async with AsyncSession(self.engine, expire_on_commit=False) as session, session.begin():
            session.add(product)
            await session.flush()
            session.add_all(
                ProductAttribute(product_id=product.id, attribute_key=key, attribute_value=value)
                for key, value in (attributes or {"material": "silver"}).items()
            )
        return product

    async def variant(
        self,
        product: Product,
        *,
        options: dict[str, str] | None = None,
        stock: tuple[int, int, int] | None = None,
        color_hex: str | None = None,
        **fields: Any,
    ) -> ProductVariant:
        values: dict[str, Any] = {"base_price": 100_000, "is_active": True} | fields
        variant = ProductVariant(
            product_id=product.id, sku=f"SKU-{uuid4().hex[:10].upper()}", **values
        )
        async with AsyncSession(self.engine, expire_on_commit=False) as session, session.begin():
            session.add(variant)
            await session.flush()
            session.add_all(
                VariantOption(
                    variant_id=variant.id,
                    option_key=key,
                    value=value,
                    hex=color_hex if key == "color" else None,
                )
                for key, value in (options or {}).items()
            )
            if stock is not None:
                total, reserved, threshold = stock
                session.add(
                    InventoryItem(
                        warehouse_id=DEFAULT_WAREHOUSE_ID,
                        product_id=product.id,
                        variant_id=variant.id,
                        total_quantity=total,
                        reserved_quantity=reserved,
                        low_stock_threshold=threshold,
                    )
                )
        return variant

    async def image(
        self,
        product: Product,
        *,
        is_main: bool = False,
        variant: ProductVariant | None = None,
        order: int = 0,
    ) -> ProductMedia:
        media = await self.make_media()
        item = ProductMedia(
            product_id=product.id,
            media_id=media.id,
            variant_id=None if variant is None else variant.id,
            is_main=is_main,
            display_order=order,
        )
        async with AsyncSession(self.engine, expire_on_commit=False) as session, session.begin():
            session.add(item)
        return item

    async def filters(self, category: Category, *items: tuple[str, str]) -> None:
        """Active CategoryFilters ``(attribute_key, filter_type)`` in the given order."""
        async with AsyncSession(self.engine) as session, session.begin():
            session.add_all(
                CategoryFilter(
                    category_id=category.id,
                    attribute_key=key,
                    label=key.title(),
                    filter_type=filter_type,
                    display_order=index,
                )
                for index, (key, filter_type) in enumerate(items)
            )

    async def set(self, model: Any, row_id: UUID, **values: Any) -> None:
        async with AsyncSession(self.engine) as session, session.begin():
            await session.execute(update(model).where(model.id == row_id).values(**values))


@pytest_asyncio.fixture
async def catalog(db_engine: AsyncEngine, make_media: MakeMedia) -> AsyncIterator[Catalog]:
    built = Catalog(db_engine, make_media)
    yield built
    ids = built.categories
    async with AsyncSession(db_engine) as session, session.begin():
        products = select(Product.id).where(Product.category_id.in_(ids))
        variants = select(ProductVariant.id).where(ProductVariant.product_id.in_(products))
        # Images uploaded through the admin API (make_media removes its own rows).
        media = list(
            await session.scalars(
                select(ProductMedia.media_id).where(ProductMedia.product_id.in_(products))
            )
        )
        await session.execute(delete(ProductMedia).where(ProductMedia.product_id.in_(products)))
        items = select(InventoryItem.id).where(InventoryItem.product_id.in_(products))
        reservations = list(
            await session.scalars(
                select(InventoryReservationItem.reservation_id).where(
                    InventoryReservationItem.inventory_item_id.in_(items)
                )
            )
        )
        await session.execute(
            delete(InventoryReservationItem).where(
                InventoryReservationItem.reservation_id.in_(reservations)
            )
        )
        await session.execute(
            delete(InventoryReservation).where(InventoryReservation.id.in_(reservations))
        )
        await session.execute(
            delete(InventoryMovement).where(InventoryMovement.inventory_item_id.in_(items))
        )
        await session.execute(delete(CartItem).where(CartItem.product_id.in_(products)))
        await session.execute(delete(InventoryItem).where(InventoryItem.product_id.in_(products)))
        await session.execute(delete(PriceHistory).where(PriceHistory.product_id.in_(products)))
        await session.execute(delete(VariantOption).where(VariantOption.variant_id.in_(variants)))
        await session.execute(delete(ProductVariant).where(ProductVariant.product_id.in_(products)))
        await session.execute(
            delete(ProductAttribute).where(ProductAttribute.product_id.in_(products))
        )
        await session.execute(delete(Product).where(Product.category_id.in_(ids)))
        await session.execute(delete(CategoryFilter).where(CategoryFilter.category_id.in_(ids)))
        await session.execute(update(Category).where(Category.id.in_(ids)).values(parent_id=None))
        await session.execute(delete(Category).where(Category.id.in_(ids)))
        await session.execute(delete(Media).where(Media.id.in_(media)))


@contextmanager
def count_queries(client: AsyncClient) -> Iterator[list[str]]:
    engine = client._transport.app.state.db_engine.sync_engine  # type: ignore[attr-defined]
    statements: list[str] = []

    def record(*args: Any) -> None:
        statements.append(args[2])

    event.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", record)


def nested_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        nested = set().union(*(nested_keys(item) for item in value.values())) if value else set()
        return set(value) | nested
    if isinstance(value, list):
        return set().union(*(nested_keys(item) for item in value)) if value else set()
    return set()
