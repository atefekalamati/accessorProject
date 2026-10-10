# CAT-09 — Category filters endpoint + CategoryFilter

**Status:** COMPLETE · **Priority:** MEDIUM · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** CAT-04 · **Level:** MEDIUM

## Objective
مدل `CategoryFilter`، endpoint عمومی `GET /categories/{slug}/filters` که فیلترها را از داده واقعی محصولات دسته می‌سازد، و `PATCH /admin/categories/{id}/filters` برای مدیریت آن‌ها.

## PRD reference
«دسته‌بندی محصولات» ✓ (Entity CategoryFilter؛ قانون «فیلترها باید براساس ویژگی‌های واقعی محصولات همان دسته ساخته شوند»؛ APIهای filters؛ AuditLog برای تغییرات فیلتر)؛ ADR-022؛ ADR-026.

## Acceptance Criteria
- [x] جدول `category_filters` (migration `20261010_0010`): `attribute_key` (≤ ۵۰)، `label` (≤ ۱۰۰)، `filter_type` (checkbox، range، color یا select، با CHECK)، `display_order` و `is_active`؛ unique `(category_id, attribute_key)` و FK `RESTRICT`.
- [x] `GET /categories/{slug}/filters`: فقط فیلترهای فعال دسته قابل نمایش، به ترتیب `display_order`. مقادیر و تعداد محصول از محصولات published و حذف‌نشده خود دسته می‌آیند: گزینه‌های color/size/model از تنوع‌های فعال و حذف‌نشده، و بقیه از ProductAttribute. فیلتر بدون مقدار حذف می‌شود.
- [x] دسته پنهان یا soft-deleted → 404 (تست SD rule). پارامتر query ناشناخته → 400. محاسبه با دو کوئری GROUP BY انجام می‌شود، پس N+1 نداریم.
- [x] `PATCH /admin/categories/{id}/filters` با `catalog:manage`: کل مجموعه (حداکثر ۳۰) جایگزین می‌شود. کلید تکراری، `range` روی کلیدی جز `price`، `color` روی کلیدی جز `color`، و فیلد ناشناخته → 400. دسته ناموجود یا حذف‌شده → 404. پاسخ `no-store` دارد.
- [x] audit `category.filters_updated` با before/after کامل. مجموعه یکسان → 200 بدون audit.
- [x] تست 401، و 403 برای customer، support و content_manager.
- [x] pytest، ruff، format و mypy سبز.

## Implementation Notes
- کد: `CategoryFilter` در `app/db/models/catalog.py`. کوئری‌ها در `CategoryRepository` و `AdminCategoryRepository`. `CategoryService.filters` و `AdminCategoryService.replace_filters`. routeها در `router.py` و `admin_router.py`.
- تست: `tests/test_category_filters.py`.
- فیلتر `price` (range) تا وقتی قیمت محصول وجود ندارد داده‌ای ندارد و در خروجی عمومی نمی‌آید. CAT-07 آن را با min/max قیمت نهایی اضافه می‌کند (ADR-026).
- endpoint GET ادمین برای فیلترها در PRD نیست و ساخته نشد. پاسخ PATCH کل مجموعه را برمی‌گرداند.

## Validation
```powershell
python -m pytest -q   # با TEST_DATABASE_URL
python -m ruff check .; python -m ruff format --check .; python -m mypy app tests
```

## Log
- 2026-10-10: COMPLETE (batch A تغییرشکل‌یافته: CAT-09، PRC-01؛ CAT-05 به‌خاطر dependency جدید `python-multipart` متوقف شد). pytest 790 passed (23 تست جدید)؛ ruff، format و mypy سبز.
