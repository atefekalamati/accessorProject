# INF-04 — Soft delete mixin & helpers

**Status:** COMPLETE (2026-09-29) · **Priority:** MEDIUM · **Estimate:** 1.5h (estimate) · **Deadline:** — · **Dependencies:** FND-04 · **Level:** MEDIUM

## Objective
`SoftDeleteMixin` (ستون `deleted_at`) و helper فیلتر رکوردهای حذف‌نشده، تا Product و Variant (CAT-02 و CAT-03) از آن استفاده کنند.

## PRD reference
«معماری سیستم» ✓ («اطلاعات سفارش‌های قبلی حتی در صورت حذف یا غیرفعال‌شدن محصول نباید از بین برود»)

## Acceptance Criteria
- [x] mixin با ستون `deleted_at` (nullable، timezone-aware) و index در `app/db/models/common.py` تعریف شده است.
- [x] helper فیلتر، رکورد soft-deleted را برنمی‌گرداند (تست integration).
- [x] اگر `User` به mixin منتقل شد، هیچ migration جدیدی لازم نشده و `test_migration_matches_sqlalchemy_metadata` سبز مانده است.

- [x] `soft_delete()` idempotent است: `deleted_at` موجود هرگز بازنویسی نمی‌شود (unit test).
- [x] وضعیت unique روی مدل‌های soft-deletable گزارش و به‌صورت ADR-015 ثبت شد؛ schema تغییر نکرد.

## Implementation Notes
`app/db/models/common.py`، `app/db/models/users.py`، `tests/test_database.py`.

## Validation
```powershell
python -m pytest   # با TEST_DATABASE_URL
python -m mypy app tests
```

## Log
- 2026-09-29: از `tasks/M1-04-soft-delete-mixin.md` منتقل شد.
- 2026-09-29: COMPLETE. `SoftDeleteMixin` (`deleted_at` با `index=True`، `is_deleted`، `soft_delete()` idempotent) و `not_deleted(model)` در `app/db/models/common.py`. `User` به mixin منتقل شد. index `ix_users_deleted_at` از naming convention همان نام را می‌گیرد، پس migration لازم نشد. تست‌ها: `tests/test_soft_delete.py` (unit) و `test_not_deleted_excludes_soft_deleted_rows` (integration). ADR-015 ثبت شد. pytest 272 passed؛ ruff، format و mypy سبز.
