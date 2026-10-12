"""Inventory constants shared by models, migrations and services (ADR-005, ADR-029)."""

from __future__ import annotations

from typing import Final

# Upper bound of one stock counter (total, reserved, low-stock threshold) per item.
MAX_STOCK_QUANTITY: Final = 1_000_000
