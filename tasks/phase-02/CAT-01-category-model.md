# CAT-01 — Category model + migration (tree, slug, status, order)

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** INF-04 · **Level:** MEDIUM

## Objective
مدل و migration دسته‌بندی: درخت با `parent_id`، slug یکتا بین رکوردهای soft-delete‌نشده، وضعیت فعال/غیرفعال و ترتیب نمایش. بدون endpoint (CAT-06 و CAT-10).

## PRD reference
«دسته‌بندی محصولات» ✓ (Entity Category، ارتباط‌ها)؛ «محصولات» ✓ (شرط انتشار: دسته soft-delete نشده)؛ ADR-015؛ ADR-021.

## Acceptance Criteria
- [x] جدول `categories` با فیلدهای PRD: `parent_id`، `title`، `slug`، `description`، `icon_key`، `image_url`، `display_order`، `is_active`، `seo_title`، `seo_description`، timestampها و `deleted_at` (SoftDeleteMixin).
- [x] `parent_id` → `categories.id` با `ON DELETE RESTRICT`؛ CHECK `parent_id <> id`. چرخه عمیق‌تر در سرویس admin (CAT-10) رد می‌شود.
- [x] slug: partial unique `uq_categories_slug` با `WHERE deleted_at IS NULL` (ADR-015) و CHECK فرمت `^[a-z0-9-]{3,120}$` (همان قاعده slug محصول).
- [x] `is_active` پیش‌فرض true، `display_order >= 0` پیش‌فرض 0، index `(parent_id, display_order)`. پنهان‌کردن دسته غیرفعال/حذف‌شده در read عمومی در CAT-06 با تست پیاده می‌شود.
- [x] مدل export در `app/db/models/__init__.py`، افزوده به `_MODELS` در `alembic/env.py`، `EXPECTED_TABLES` و `HEAD_REVISION` در `tests/test_database.py` به‌روز.
- [x] migration جدید `20261010_0006`، upgrade/downgrade سالم و `compare_metadata` بدون تفاوت.
- [x] pytest، ruff، format و mypy سبز.

## Implementation Notes
`app/db/models/catalog.py` (جدید؛ Product و ProductVariant در CAT-02/03 به همین فایل اضافه می‌شوند)، `alembic/versions/20261010_0006_create_categories.py`، `tests/test_catalog_models.py` (جدید).

## Validation
```powershell
python -m pytest -q   # با TEST_DATABASE_URL
python -m ruff check .; python -m ruff format --check .; python -m mypy app tests
```

## Log
- 2026-10-10: COMPLETE (batch SEC-07/SEC-06/CAT-01..03). تست‌ها: پیش‌فرض‌ها، درخت و ترتیب، FK والد، CHECK خود-والد، RESTRICT حذف سخت والد، slug تکراری، آزادشدن slug بعد از soft delete، CHECKهای عنوان/slug/ترتیب و فهرست ستون‌ها. تصمیم‌های کم‌اثر در ADR-021.
