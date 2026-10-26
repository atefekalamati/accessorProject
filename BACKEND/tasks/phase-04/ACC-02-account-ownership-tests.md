# ACC-02 — Account ownership tests

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** ACC-01 · **Level:** MEDIUM

## Objective
تست IDOR برای همه endpointهای مالکیت‌دار مشتری.

## PRD reference
«سفارش‌ها» ✓، «آدرس» ✓، «سبد خرید» ✓.

## Acceptance Criteria
- [x] دو کاربر: سفارش، لغو، پرداخت، آدرس و خط سبد دیگری → 404 و بدون اثر جانبی.
- [x] فهرست‌ها هیچ ردیفی از کاربر دیگر ندارند.

## Implementation Notes
فقط `tests/test_account_ownership.py`.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-10-26: `tests/test_account_ownership.py` (batch 2).
  - مهاجم روی همه این‌ها 404 می‌گیرد و snapshot قربانی بدون تغییر می‌ماند:
    - جزئیات، لغو و init پرداخت سفارش
    - GET، PATCH و DELETE آدرس
    - PATCH و DELETE خط سبد
    - checkout validate با آدرس قربانی
  - فهرست‌های سفارش، آدرس و سبد ردیف قربانی را ندارند. مهمان هم به خط سبد مشتری دسترسی ندارد.
  - هیچ IDOR پیدا نشد. pytest سبز. COMPLETE.

