from __future__ import annotations

from enum import StrEnum
from typing import Final
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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
from app.db.models.common import TimestampMixin, UUIDPrimaryKeyMixin
from app.shared.inventory import MAX_STOCK_QUANTITY

# The v1 default warehouse, inserted by migration 20261010_0013 (ADR-005).
DEFAULT_WAREHOUSE_ID: Final = uuid5(NAMESPACE_URL, "project-ak:default_warehouse")


class WarehouseStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


WAREHOUSE_STATUSES_SQL: Final = ", ".join(f"'{status.value}'" for status in WarehouseStatus)


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
