# CAT-03 — ProductVariant model (SKU, active, purchasable; no stock column)

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** CAT-02, ADR-005 · **Level:** MEDIUM

## Objective
مدل و migration تنوع محصول: SKU یکتا بین رکوردهای soft-delete‌نشده، فعال/قابل‌خرید، ترتیب نمایش و soft delete. بدون ستون موجودی (ADR-005) و بدون قیمت (PRC-01). `VariantOption` در CAT-04.

## PRD reference
«محصولات» ✓ (Entity ProductVariant، قاعده SKU، soft delete)؛ «معماری سیستم»؛ ADR-005، ADR-015، ADR-021.

## Acceptance Criteria
- [x] جدول `product_variants` با `product_id`، `sku`، `display_order`، `is_active`، `is_purchasable`، timestampها و `deleted_at`.
- [x] بدون ستون موجودی و قیمت (تست فهرست ستون‌ها). موجودی فقط در InventoryItem (INV-01)؛ قیمت در PRC-01.
- [x] SKU: partial unique `uq_product_variants_sku` (`WHERE deleted_at IS NULL`، سراسری بین همه محصولات) و CHECK فرمت نرمال‌شده `^[A-Z0-9-]{1,64}$`. نرمال‌سازی trim/upper در API (CAT-11).
- [x] `product_id` → `products.id` با `RESTRICT`: محصول ارجاع‌شده حذف سخت نمی‌شود (تکمیل معیار CAT-02).
- [x] `is_active` پیش‌فرض false (تنوع بدون قیمت معتبر نباید فعال باشد)، `is_purchasable` پیش‌فرض true، `display_order >= 0`، index `(product_id, display_order)`.
- [x] export، `_MODELS`، `EXPECTED_TABLES` و `HEAD_REVISION` به‌روز؛ migration `20261010_0008` سالم و `compare_metadata` بدون تفاوت.
- [x] pytest، ruff، format و mypy سبز.

## Implementation Notes
`app/db/models/catalog.py`، `alembic/versions/20261010_0008_create_product_variants.py`، `tests/test_catalog_models.py`.

## Validation
```powershell
python -m pytest -q   # با TEST_DATABASE_URL
python -m ruff check .; python -m ruff format --check .; python -m mypy app tests
```

## Log
- 2026-10-10: COMPLETE (پایان batch SEC-07/SEC-06/CAT-01..03). pytest 667 passed؛ ruff، format و mypy سبز. تست‌ها: پیش‌فرض‌ها، چند تنوع با ترتیب، FK محصول، RESTRICT حذف سخت محصول ارجاع‌شده، SKU تکراری بین دو محصول، آزادشدن SKU بعد از soft delete، CHECKهای فرمت SKU و ترتیب، و نبود ستون موجودی/قیمت.
