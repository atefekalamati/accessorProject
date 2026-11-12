# CAT-02 — Product model + soft delete + draft/published/archived

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** CAT-01, INF-04 · **Level:** MEDIUM

## Objective
مدل و migration محصول با وضعیت انتشار، slug یکتا بین رکوردهای soft-delete‌نشده و soft delete. بدون endpoint (CAT-08 و CAT-11). `ProductAttribute` در CAT-04 و `ProductMedia` در CAT-05.

## PRD reference
«محصولات» ✓ (Entity Product، قوانین وضعیت، slug، soft delete)؛ «جزئیات محصول» ✓؛ ADR-015، ADR-020، ADR-021.

## Acceptance Criteria
- [x] جدول `products` با فیلدهای PRD: `category_id`، `title`، `slug`، `description`، `status`، `published_at`، `is_featured`، `created_by`، `updated_by`، timestampها و `deleted_at`.
- [x] `status` فقط `draft`/`published`/`archived` (CHECK + `ProductStatus`)، پیش‌فرض `draft`. گراف انتقال وضعیت در سرویس CAT-11 است.
- [x] CHECK: محصول `published` حتماً `published_at` دارد؛ `published_at` بعد از برگشت به draft حفظ می‌شود (تست).
- [x] slug: partial unique `uq_products_slug` (`WHERE deleted_at IS NULL`، ADR-015) و CHECK فرمت `^[a-z0-9-]{3,120}$`. slug رکورد soft-deleted دوباره قابل استفاده است.
- [x] `category_id` → `categories.id` با `RESTRICT` (حذف سخت دسته دارای محصول ممکن نیست)؛ `created_by`/`updated_by` → `users.id` با `SET NULL` (مثل `audit_logs.actor_user_id`).
- [x] referenced products soft-deleted only: حذف سخت محصول ارجاع‌شده در DB با FK `RESTRICT` از جدول‌های ارجاع‌دهنده رد می‌شود (اولین ارجاع‌دهنده: `product_variants` در CAT-03، تست همان‌جا). حذف API همیشه soft delete است (CAT-11).
- [x] index برای لیست عمومی: `(status, published_at)` و `category_id`.
- [x] export، `_MODELS`، `EXPECTED_TABLES` و `HEAD_REVISION` به‌روز؛ migration `20261010_0007` سالم و `compare_metadata` بدون تفاوت.
- [x] pytest، ruff، format و mypy سبز.

## Implementation Notes
`app/db/models/catalog.py`، `alembic/versions/20261010_0007_create_products.py`، `tests/test_catalog_models.py`.

## Validation
```powershell
python -m pytest -q   # با TEST_DATABASE_URL
python -m ruff check .; python -m ruff format --check .; python -m mypy app tests
```

## Log
- 2026-10-10: COMPLETE (batch SEC-07/SEC-06/CAT-01..03). pytest 654 passed؛ ruff، format و mypy سبز. تست‌ها: پیش‌فرض draft، FK دسته و RESTRICT، هر سه وضعیت، CHECK `published_at`، حفظ `published_at` بعد از unpublish، slug تکراری/آزادشدن بعد از soft delete، `SET NULL` برای created_by/updated_by، CHECKهای عنوان/slug/status و فهرست ستون‌ها.
