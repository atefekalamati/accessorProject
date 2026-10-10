# INV-01 — Warehouse (1 default) + InventoryItem per variant+warehouse

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** CAT-03, ADR-005 · **Level:** HIGH

## Objective
جدول‌های `warehouses` (با یک انبار پیش‌فرض که migration درج می‌کند) و `inventory_items` (موجودی per variant و انبار). بدون endpoint و بدون رزرو: تنظیم موجودی در INV-02/INV-08، رزرو در INV-04.

## PRD reference
«موجودی و رزرو» ✓ (Entityهای Warehouse و InventoryItem، قوانین کسب‌وکار، کنترل‌های امنیتی)؛ «محصولات» ✓ (تنوع بدون InventoryItem → `out_of_stock`؛ موجودی در این بخش ویرایش نمی‌شود)؛ ADR-005، ADR-007، ADR-021؛ M2.2-PLAN.md.

## Acceptance Criteria
- [x] `warehouses`: `name` (۱..۱۰۰، not blank)، `city` (nullable، ≤ ۱۰۰، not blank)، `status` (`active`/`inactive`، CHECK)، `is_default` با partial unique (`WHERE is_default`) و CHECK «انبار پیش‌فرض فعال است»، timestamps.
- [x] `inventory_items`: `warehouse_id`، `product_id`، `variant_id`؛ composite FK `(variant_id, product_id)` → `product_variants(id, product_id)`؛ همه FKها `RESTRICT` (ADR-021)؛ unique `(variant_id, warehouse_id)`؛ index روی `product_id`.
- [x] `total_quantity`، `reserved_quantity`، `low_stock_threshold`: INTEGER پیش‌فرض 0 با CHECK `0 ≤ total ≤ MAX_STOCK_QUANTITY`، `0 ≤ reserved ≤ total`، `0 ≤ threshold ≤ MAX_STOCK_QUANTITY`. ProductVariant ستون موجودی ندارد (ADR-005).
- [x] migration `20261010_0013`: انبار پیش‌فرض با id ثابت uuid5 درج می‌شود؛ downgrade/upgrade دوباره ردیف تکراری نمی‌سازد.
- [x] ثابت `MAX_STOCK_QUANTITY` در `app/shared/inventory.py` و `DEFAULT_WAREHOUSE_ID` در مدل.
- [x] export، `_MODELS`، `EXPECTED_TABLES` و `HEAD_REVISION` به‌روز؛ `compare_metadata` بدون تفاوت.
- [x] تست‌ها: پیش‌فرض‌ها، هر CHECK (مرز داخل/خارج)، unique، انبار پیش‌فرض دوم و پیش‌فرض غیرفعال رد، variant از محصول دیگر رد، حذف سخت variant دارای InventoryItem رد، round-trip migration.
- [x] pytest، ruff، format و mypy سبز.

## Implementation Notes
- کد: `app/db/models/inventory.py`، `app/shared/inventory.py`، `alembic/versions/20261010_0013_create_warehouses_and_inventory_items.py`، `app/db/models/__init__.py`، `alembic/env.py`.
- تست: `tests/test_inventory_models.py`؛ به‌روزرسانی `tests/test_database.py`.
- `reserved_quantity` از Entity PRD ✓ است: شمارنده رزروهای فعال که INV-04 تا INV-06 زیر `FOR UPDATE` نگه می‌دارند. CHECK `reserved ≤ total` آخرین backstop در برابر oversell است.
- InventoryItem soft delete ندارد؛ variant حذف‌شده موجودی‌اش را نگه می‌دارد (SD rule در write ارجاع‌دهنده اعمال می‌شود).
- قواعد برای مصرف‌کننده‌ها (ADR-029): invariant شمارنده رزرو، آزادسازی lazy رزرو منقضی زیر lock، ترتیب lock `ORDER BY variant_id, warehouse_id`، بررسی شرط در سرویس قبل از CHECK (409/422 نه 500)، commit با یک UPDATE روی total و reserved.
- برای task مدیریت انبار در آینده: انبار پیش‌فرض حذف یا غیرپیش‌فرض نشود (فقط سرویس، بدون trigger)؛ index با `warehouse_id` در ابتدای کلید بعد از v1 چندانباره لازم می‌شود.
- **ریسک‌ها:** انبار پیش‌فرض تکراری (partial unique)؛ InventoryItem با variant محصول دیگر (composite FK)؛ موجودی منفی یا رزرو بیش از کل (CHECK)؛ حذف سخت variant/انبار ارجاع‌شده (RESTRICT)؛ migration تکرارناپذیر (id ثابت).
- **Rollback:** `alembic downgrade -1` (فقط با تأیید صریح روی دیتابیس واقعی؛ جدول‌ها هنوز داده تولیدی ندارند)، سپس `git revert`.

## Validation
```powershell
python -m pytest -q   # با TEST_DATABASE_URL
python -m ruff check .; python -m ruff format --check .; python -m mypy app tests
```

## Log
- 2026-10-10: جلو آمد (قبل از CAT-11): جزئیات admin محصول وضعیت موجودی هر تنوع را می‌خواهد.
- 2026-10-10: بازبینی plan توسط subagent مستقل: APPROVE WITH CHANGES، بدون blocker و بدون مورد ارجاع به کاربر. اعمال شد: ADR-029 (invariant شمارنده، رزرو منقضی، ترتیب lock، رفتار سرویس قبل از CHECK، قاعده threshold، چند انبار، حفاظت انبار پیش‌فرض) و `max_purchasable` در INV-03.
- 2026-10-10: بازبینی diff توسط subagent مستقل: APPROVE WITH CHANGES. اعمال شد: assert نام constraint در همه تست‌های IntegrityError، CHECK `city_not_blank`، تست طول نام. موارد آینده (index `warehouse_id`، حفاظت انبار پیش‌فرض، تست commit تک‌UPDATE در INV-05) در Notes و ADR-029 ثبت شد. چک‌لیست: §5 pass، بقیه N/A.
- 2026-10-10: COMPLETE. pytest 935 passed (کل suite)، ruff، format و mypy سبز.
