# CAT-04 — Attributes & values (color/size/model)

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** CAT-03 · **Level:** MEDIUM

## Objective
مدل و migration ویژگی‌های محصول (`ProductAttribute`، جفت key/value نمایشی) و گزینه‌های تنوع (`VariantOption`، کلیدهای color/size/model). بدون endpoint (CAT-08، CAT-11).

## PRD reference
«محصولات» ✓ (Entity VariantOption و ProductAttribute، قاعده گزینه‌های تنوع)؛ «جزئیات محصول» ✓ (`options` در پاسخ)؛ ADR-020، ADR-021.

## Acceptance Criteria
- [x] جدول `variant_options`: `variant_id`، `option_key` (CHECK فقط `color`/`size`/`model`، `VariantOptionKey`)، `value` (۱ تا ۵۰ کاراکتر، CHECK غیرخالی)؛ unique `(variant_id, option_key)` (حداکثر یک مقدار برای هر کلید).
- [x] جدول `product_attributes`: `product_id`، `attribute_key` (≤ ۵۰)، `attribute_value` (≤ ۲۰۰)، `display_order`؛ unique `(product_id, attribute_key)`.
- [x] FKها `RESTRICT` (ADR-021). index `(option_key, value)` و `attribute_key` برای فیلترهای بعدی (CAT-07/09).
- [x] قواعد سطح سرویس (CAT-11، نه DB): یکتایی ترکیب گزینه‌ها بین تنوع‌های soft-delete‌نشده یک محصول، حداکثر یک تنوع بدون گزینه، حداکثر ۵۰ ویژگی و جایگزینی کل مجموعه.
- [x] export، `_MODELS`، `EXPECTED_TABLES` و `HEAD_REVISION` به‌روز؛ migration `20261010_0009` سالم و `compare_metadata` بدون تفاوت.
- [x] pytest، ruff، format و mypy سبز.

## Implementation Notes
`app/db/models/catalog.py`، `alembic/versions/20261010_0009_create_attributes_and_variant_options.py`، `tests/test_catalog_models.py`.

## Validation
```powershell
python -m pytest -q   # با TEST_DATABASE_URL
python -m ruff check .; python -m ruff format --check .; python -m mypy app tests
```

## Log
- 2026-10-10: COMPLETE (batch ۲ جلسه: CAT-04/CAT-06). pytest 681 passed؛ ruff، format و mypy سبز. تصمیم‌های کم‌اثر (ADR-021): یک مقدار برای هر کلید ویژگی در هر محصول؛ طول کلید ۵۰ و مقدار ۲۰۰؛ این دو جدول timestamp ندارند (PRD ندارد و تغییرات در AuditLog ثبت می‌شوند).
