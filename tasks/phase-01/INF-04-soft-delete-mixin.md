# INF-04 — Soft delete mixin & helpers

**Status:** NOT_STARTED · **Priority:** MEDIUM · **Estimate:** 1.5h (estimate) · **Deadline:** — · **Dependencies:** FND-04

## Objective
`SoftDeleteMixin` (ستون `deleted_at`) و helper فیلتر رکوردهای حذف‌نشده، تا Product و Variant (CAT-02 و CAT-03) از آن استفاده کنند.

## PRD reference
«معماری سیستم» ✓ («اطلاعات سفارش‌های قبلی حتی در صورت حذف یا غیرفعال‌شدن محصول نباید از بین برود»)

## Acceptance Criteria
- [ ] mixin با ستون `deleted_at` (nullable، timezone-aware) و index در `app/db/models/common.py` تعریف شده است.
- [ ] helper فیلتر، رکورد soft-deleted را برنمی‌گرداند (تست integration).
- [ ] اگر `User` به mixin منتقل شد، هیچ migration جدیدی لازم نشده و `test_migration_matches_sqlalchemy_metadata` سبز مانده است.

## Implementation Notes
`app/db/models/common.py`، `app/db/models/users.py`، `tests/test_database.py`.

## Validation
```powershell
python -m pytest   # با TEST_DATABASE_URL
python -m mypy app tests
```

## Log
- 2026-09-29: از `tasks/M1-04-soft-delete-mixin.md` منتقل شد.
