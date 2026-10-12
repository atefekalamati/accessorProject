# CAT-06 — Public GET /categories, /categories/{slug}

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** CAT-01 · **Level:** MEDIUM

## Objective
API عمومی دسته‌بندی: درخت دسته‌های قابل نمایش و جزئیات یک دسته با breadcrumb و زیرمجموعه‌ها. بدون محصولات (CAT-07) و فیلترها (CAT-09).

## PRD reference
«دسته‌بندی محصولات» ✓ (APIهای `GET /categories` و `GET /categories/{slug}`، قانون «دسته غیرفعال در خروجی عمومی نمایش داده نشود»)؛ ADR-022؛ SD rule (PLAN.md).

## Acceptance Criteria
- [x] `GET /api/v1/categories` درخت دسته‌های قابل نمایش را برمی‌گرداند (`{"items": [...]}`)، با ترتیب `display_order` و سپس `id`.
- [x] «قابل نمایش» یعنی خود دسته و همه اجدادش فعال و soft-delete‌نشده باشند (ADR-022). این قاعده با یک recursive CTE در SQL اجرا می‌شود، پس N+1 نداریم.
- [x] `GET /api/v1/categories/{slug}` فیلدهای عمومی، breadcrumb (از ریشه تا خود دسته) و زیرمجموعه‌های مستقیم قابل نمایش را برمی‌گرداند.
- [x] دسته پنهان (غیرفعال، soft-deleted یا زیر جد پنهان)، slug ناموجود یا slug با فرمت نامعتبر → 404 `NOT_FOUND` (تست SD rule).
- [x] فیلدهای داخلی (`is_active`، `deleted_at`، `display_order` و timestampها) در خروجی نیستند. پارامتر query ناشناخته → 400.
- [x] مهمان بدون token دسترسی دارد.
- [x] pytest، ruff، format و mypy سبز.

## Implementation Notes
`app/modules/catalog/{schemas,repository,service,dependencies,router}.py`، ثبت در `app/api/v1/router.py`، `tests/test_categories_public.py`.
فرض: تعداد دسته‌ها کوچک است (فروشگاه اکسسوری)، پس هر دو endpoint کل مجموعه قابل نمایش را با یک کوئری می‌خوانند و درخت را در حافظه می‌سازند.

## Validation
```powershell
python -m pytest -q   # با TEST_DATABASE_URL
python -m ruff check .; python -m ruff format --check .; python -m mypy app tests
```

## Log
- 2026-10-10: COMPLETE (batch CAT-06/CAT-10). pytest 693 passed (12 تست جدید)؛ ruff، format و mypy سبز.
