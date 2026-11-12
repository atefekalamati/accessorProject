from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Final
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.shared.inventory import MAX_STOCK_QUANTITY

# The v1 default warehouse, inserted by migration 20261010_0013 (ADR-005).
DEFAULT_WAREHOUSE_ID: Final = uuid5(NAMESPACE_URL, "project-ak:default_warehouse")


class WarehouseStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


WAREHOUSE_STATUSES_SQL: Final = ", ".join(f"'{status.value}'" for status in WarehouseStatus)


class MovementType(StrEnum):
    """Why a stock counter changed (PRD «موجودی و رزرو» ✓, InventoryMovement)."""

    INCREASE = "increase"
    DECREASE = "decrease"
    RESERVE = "reserve"
    RELEASE = "release"
    COMMIT = "commit"
    CORRECTION = "correction"
    RETURN = "return"


MOVEMENT_TYPES_SQL: Final = ", ".join(f"'{kind.value}'" for kind in MovementType)
MAX_MOVEMENT_REASON_LENGTH: Final = 500
# What a movement may point at (reservation flows in INV-04..06, returns later).
MOVEMENT_REFERENCE_TYPES: Final = ("reservation", "order", "payment", "return")
MOVEMENT_REFERENCE_TYPES_SQL: Final = ", ".join(f"'{kind}'" for kind in MOVEMENT_REFERENCE_TYPES)
# Each type moves the counters in one fixed way; ``quantity`` is always |change| > 0.
MOVEMENT_DELTAS_SQL: Final = (
    "(movement_type IN ('increase', 'return')"
    " AND total_after = total_before + quantity AND reserved_after = reserved_before)"
    " OR (movement_type = 'decrease'"
    " AND total_after = total_before - quantity AND reserved_after = reserved_before)"
    " OR (movement_type = 'correction'"
    " AND abs(total_after - total_before) = quantity AND reserved_after = reserved_before)"
    " OR (movement_type = 'reserve'"
    " AND reserved_after = reserved_before + quantity AND total_after = total_before)"
    " OR (movement_type = 'release'"
    " AND reserved_after = reserved_before - quantity AND total_after = total_before)"
    " OR (movement_type = 'commit' AND total_after = total_before - quantity"
    " AND reserved_after = reserved_before - quantity)"
)


class Warehouse(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A stock location; v1 has exactly one active default warehouse (ADR-005)."""

    __tablename__ = "warehouses"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint("city IS NULL OR length(trim(city)) > 0", name="city_not_blank"),
        CheckConstraint(f"status IN ({WAREHOUSE_STATUSES_SQL})", name="valid_status"),
        CheckConstraint(
            f"NOT is_default OR status = '{WarehouseStatus.ACTIVE.value}'",
            name="default_is_active",
        ),
        # At most one default warehouse.
        Index(
            "uq_warehouses_default", "is_default", unique=True, postgresql_where=text("is_default")
        ),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default=WarehouseStatus.ACTIVE,
        server_default=WarehouseStatus.ACTIVE.value,
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )


class InventoryItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Stock of one variant in one warehouse; the only place stock lives (ADR-005).

    ``reserved_quantity`` counts active reservations (INV-04..06 keep it under
    ``SELECT ... FOR UPDATE``); free stock is ``total_quantity - reserved_quantity``.
    """

    __tablename__ = "inventory_items"
    __table_args__ = (
        CheckConstraint(
            f"total_quantity BETWEEN 0 AND {MAX_STOCK_QUANTITY}", name="total_quantity_range"
        ),
        # Last line of defence against overselling.
        CheckConstraint(
            "reserved_quantity BETWEEN 0 AND total_quantity", name="reserved_quantity_range"
        ),
        CheckConstraint(
            f"low_stock_threshold BETWEEN 0 AND {MAX_STOCK_QUANTITY}",
            name="low_stock_threshold_range",
        ),
        # The variant must belong to the stored product.
        ForeignKeyConstraint(
            ["variant_id", "product_id"],
            ["product_variants.id", "product_variants.product_id"],
            name="fk_inventory_items_variant_id_product_variants",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("variant_id", "warehouse_id"),
        Index("ix_inventory_items_product_id", "product_id"),
    )

    warehouse_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
    )
    product_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    variant_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    total_quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    reserved_quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    low_stock_threshold: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )


class InventoryMovement(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One change of an InventoryItem's counters, with both sides of it (INV-02, ADR-034).

    Append-only: every manual adjustment, reservation, release and commit writes one row in
    the same transaction as the counter change.
    """

    __tablename__ = "inventory_movements"
    __table_args__ = (
        CheckConstraint(f"movement_type IN ({MOVEMENT_TYPES_SQL})", name="valid_movement_type"),
        CheckConstraint(f"quantity BETWEEN 1 AND {MAX_STOCK_QUANTITY}", name="quantity_range"),
        CheckConstraint(
            f"total_before BETWEEN 0 AND {MAX_STOCK_QUANTITY}"
            f" AND total_after BETWEEN 0 AND {MAX_STOCK_QUANTITY}",
            name="total_range",
        ),
        CheckConstraint(
            "reserved_before BETWEEN 0 AND total_before"
            " AND reserved_after BETWEEN 0 AND total_after",
            name="reserved_range",
        ),
        CheckConstraint(MOVEMENT_DELTAS_SQL, name="consistent_delta"),
        CheckConstraint(
            "(reference_type IS NULL) = (reference_id IS NULL)", name="reference_complete"
        ),
        CheckConstraint(
            f"reference_type IS NULL OR reference_type IN ({MOVEMENT_REFERENCE_TYPES_SQL})",
            name="valid_reference_type",
        ),
        # Reservation flows always say which reservation; manual changes always say why.
        CheckConstraint(
            "movement_type NOT IN ('reserve', 'release', 'commit') OR reference_id IS NOT NULL",
            name="reservation_has_reference",
        ),
        CheckConstraint(
            "movement_type NOT IN ('increase', 'decrease', 'correction') OR reason IS NOT NULL",
            name="manual_has_reason",
        ),
        CheckConstraint(
            f"reason IS NULL OR length(trim(reason)) BETWEEN 1 AND {MAX_MOVEMENT_REASON_LENGTH}",
            name="reason_length",
        ),
        Index("ix_inventory_movements_item_created_at", "inventory_item_id", "created_at", "id"),
        Index("ix_inventory_movements_reference", "reference_type", "reference_id"),
        # One reserve, and one release or commit, per item and reservation (ADR-036).
        Index(
            "uq_inventory_movements_reservation_reserve",
            "inventory_item_id",
            "reference_id",
            unique=True,
            postgresql_where=text("reference_type = 'reservation' AND movement_type = 'reserve'"),
        ),
        Index(
            "uq_inventory_movements_reservation_close",
            "inventory_item_id",
            "reference_id",
            unique=True,
            postgresql_where=text(
                "reference_type = 'reservation' AND movement_type IN ('release', 'commit')"
            ),
        ),
    )

    inventory_item_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("inventory_items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    movement_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # Size of the change, always positive; the direction is in the before/after pairs.
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    total_before: Mapped[int] = mapped_column(Integer, nullable=False)
    total_after: Mapped[int] = mapped_column(Integer, nullable=False)
    reserved_before: Mapped[int] = mapped_column(Integer, nullable=False)
    reserved_after: Mapped[int] = mapped_column(Integer, nullable=False)
    # What caused it, e.g. ("reservation", <id>); NULL for manual adjustments.
    reference_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    reference_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(MAX_MOVEMENT_REASON_LENGTH), nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


class ReservationStatus(StrEnum):
    """Lifecycle of a reservation (PRD «موجودی و رزرو» ✓). ``active`` past ``expires_at`` is
    already inactive for every check; the job only cleans it up to ``expired`` (ADR-036)."""

    ACTIVE = "active"
    RELEASED = "released"
    COMMITTED = "committed"
    EXPIRED = "expired"


class ReservationItemStatus(StrEnum):
    """Per-item state: changed only under the item's row lock, so a counter moves once."""

    ACTIVE = "active"
    RELEASED = "released"
    COMMITTED = "committed"


RESERVATION_STATUSES_SQL: Final = ", ".join(f"'{s.value}'" for s in ReservationStatus)
RESERVATION_ITEM_STATUSES_SQL: Final = ", ".join(f"'{s.value}'" for s in ReservationItemStatus)


class InventoryReservation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Stock held for one order for a limited time (INV-04, ADR-007, ADR-036).

    Valid in ``[created_at, expires_at)``. ``order_id`` references the order (ORD-01).
    """

    __tablename__ = "inventory_reservations"
    __table_args__ = (
        CheckConstraint(f"status IN ({RESERVATION_STATUSES_SQL})", name="valid_status"),
        CheckConstraint(
            "(status = 'committed') = (committed_at IS NOT NULL)", name="committed_has_time"
        ),
        CheckConstraint(
            "(status IN ('released', 'expired')) = (released_at IS NOT NULL)",
            name="released_has_time",
        ),
        # At most one live reservation per order: active, or committed for good (ADR-036).
        Index(
            "uq_inventory_reservations_live_order",
            "order_id",
            unique=True,
            postgresql_where=text("status IN ('active', 'committed') AND order_id IS NOT NULL"),
        ),
        Index("ix_inventory_reservations_status_expires_at", "status", "expires_at"),
    )

    order_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=True,
    )
    cart_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=True)
    user_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(10), nullable=False, default=ReservationStatus.ACTIVE, server_default="active"
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InventoryReservationItem(UUIDPrimaryKeyMixin, Base):
    """Units of one InventoryItem held by a reservation (INV-04, ADR-036)."""

    __tablename__ = "inventory_reservation_items"
    __table_args__ = (
        CheckConstraint(f"quantity BETWEEN 1 AND {MAX_STOCK_QUANTITY}", name="quantity_range"),
        CheckConstraint(f"status IN ({RESERVATION_ITEM_STATUSES_SQL})", name="valid_status"),
        CheckConstraint(
            "(status = 'released') = (released_at IS NOT NULL)", name="released_has_time"
        ),
        UniqueConstraint("reservation_id", "inventory_item_id"),
        ForeignKeyConstraint(
            ["variant_id", "product_id"],
            ["product_variants.id", "product_variants.product_id"],
            name="fk_inventory_reservation_items_variant_id_product_variants",
            ondelete="RESTRICT",
        ),
        # Lookups of what is still held on an item (availability, lazy release).
        Index(
            "ix_inventory_reservation_items_active_item",
            "inventory_item_id",
            postgresql_where=text("status = 'active'"),
        ),
        Index("ix_inventory_reservation_items_reservation_id", "reservation_id"),
    )

    # Explicit names: the convention's would pass PostgreSQL's 63-character limit.
    reservation_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "inventory_reservations.id",
            ondelete="RESTRICT",
            name="fk_inventory_reservation_items_reservation_id",
        ),
        nullable=False,
    )
    inventory_item_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "inventory_items.id",
            ondelete="RESTRICT",
            name="fk_inventory_reservation_items_inventory_item_id",
        ),
        nullable=False,
    )
    product_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    variant_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(10), nullable=False, default=ReservationItemStatus.ACTIVE, server_default="active"
    )
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
