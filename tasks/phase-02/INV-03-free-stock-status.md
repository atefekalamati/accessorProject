# INV-03 — Pure free-stock & stock-status functions

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** INV-01 · **Level:** HIGH

## Objective
توابع خالص و unit-testable برای موجودی آزاد، حداکثر تعداد قابل خرید و وضعیت `in_stock`/`low_stock`/`out_of_stock` per variant و برای کل محصول. مصرف‌کننده‌ها: CAT-11 (جزئیات admin)، CAT-07/CAT-08، INV-07، CART و ORD.

## PRD reference
«موجودی و رزرو» ✓ (`free = total − active reservations`؛ خروجی‌ها؛ «تست واحد برای محاسبه موجودی آزاد و وضعیت low_stock»)؛ «محصولات» ✓ و CAT-00 ردیف ۸ و ۹ (بدون InventoryItem → out؛ وضعیت کلی محصول از تنوع‌ها)؛ ADR-005، ADR-007.

## Acceptance Criteria
- [x] `app/modules/inventory/stock.py`: `StockStatus` (StrEnum)، `StockLevel` (frozen dataclass: total، reserved، low_stock_threshold)، `free_quantity(level)`، `max_purchasable(level)`، `stock_status(level | None)`، `variant_level(items)` (جمع چند انبار؛ لیست خالی → None) و `product_stock_status(statuses)`.
- [x] `free = total − reserved`؛ شمارنده منفی یا reserved > total → `ValueError` (ADR-029؛ clamp نمی‌شود تا نقض invariant پنهان نماند).
- [x] وضعیت: `free == 0` → out؛ `free ≤ threshold` → low؛ وگرنه in. بدون InventoryItem → out.
- [x] وضعیت محصول: بهترین وضعیت بین تنوع‌ها (in > low > out)؛ بدون تنوع → out. فیلتر تنوع فعال/قابل‌خرید با فراخواننده است.
- [x] unit test جدولی شامل مرزهای threshold (free = threshold و threshold + 1)، threshold صفر، reserved = total، ورودی منفی، چند انبار.
- [x] ruff، format و mypy سبز؛ pytest سبز.

## Implementation Notes
- تابع ORM یا DB نمی‌خواند؛ `StockLevel.from_item(item)` فقط سه ستون InventoryItem را کپی می‌کند.
- **ریسک‌ها:** off-by-one در مرز threshold (تست مرزی)؛ داده خراب (`ValueError` + CHECK در DB)؛ نمایش «موجود» برای تنوع بدون InventoryItem (None → out).
- **Rollback:** `git revert` (بدون schema).

## Validation
```powershell
python -m pytest -q tests/test_inventory_stock.py
python -m ruff check .; python -m ruff format --check .; python -m mypy app tests
```

## Log
- 2026-10-10: plan همراه INV-01 بازبینی شد (APPROVE WITH CHANGES): `max_purchasable` اضافه شد؛ داده ناسازگار → `ValueError` به‌جای clamp (ADR-029).
- 2026-10-10: بازبینی diff توسط subagent مستقل: APPROVE WITH CHANGES. اعمال شد: هم‌راستاکردن AC با ADR-029 (بدون clamp)، تست جمع threshold چند انبار. یادداشت برای مصرف‌کننده‌ها: `ValueError` فقط با دورزدن CHECK رخ می‌دهد و در CAT-07/08 به 500 تبدیل می‌شود (به 4xx تبدیل نشود)؛ INV-04 باید `StockLevel` را از ردیف‌های قفل‌شده با `FOR UPDATE` و بعد از آزادسازی رزرو منقضی بسازد. چک‌لیست: §9 pass، بقیه N/A.
- 2026-10-10: COMPLETE. 30 تست واحد؛ pytest 938 passed؛ ruff، format و mypy سبز.
