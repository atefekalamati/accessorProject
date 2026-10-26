# ADM-03 — Customer list/detail (admin, support)

**Status:** COMPLETE · **Priority:** MEDIUM · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** ADM-00 · **Level:** MEDIUM

## Objective
`GET /admin/customers` و `GET /admin/customers/{id}`.

## PRD reference
«مشتریان» ✓؛ D38 (ADR-053).

## Acceptance Criteria
- [x] فهرست: موبایل ماسک‌شده، `q`، `status`، صفحه‌بندی.
- [x] جزئیات: موبایل کامل، آدرس‌ها، تعداد و جمع فروش موفق، ۱۰ سفارش آخر؛ audit `customer.viewed` در هر مشاهده.
- [x] هیچ session، OTP یا token در پاسخ نیست (تست کلیدها)؛ مجوز `customers:read`.

## Implementation Notes
`app/modules/admin/`.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-10-26: پیاده‌سازی (batch 3).
  - فهرست مشتریان (فقط نقش customer، حذف‌نشده) با موبایل ماسک‌شده.
  - جزئیات با موبایل کامل، آدرس‌ها، تعداد سفارش، جمع فروش موفق و ۱۰ سفارش آخر.
  - audit `customer.viewed` در همان تراکنش GET.
  - مجوز `customers:read`. Level MEDIUM. COMPLETE.

