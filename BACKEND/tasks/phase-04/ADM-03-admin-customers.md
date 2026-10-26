# ADM-03 — Customer list/detail (admin, support)

**Status:** NOT_STARTED · **Priority:** MEDIUM · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** ADM-00 · **Level:** MEDIUM

## Objective
`GET /admin/customers` و `GET /admin/customers/{id}`.

## PRD reference
«مشتریان» ✓؛ D38 (ADR-053).

## Acceptance Criteria
- [ ] فهرست: موبایل ماسک‌شده، `q`، `status`، صفحه‌بندی.
- [ ] جزئیات: موبایل کامل، آدرس‌ها، تعداد و جمع فروش موفق، ۱۰ سفارش آخر؛ audit `customer.viewed` در هر مشاهده.
- [ ] هیچ session، OTP یا token در پاسخ نیست (تست کلیدها)؛ مجوز `customers:read`.

## Implementation Notes
`app/modules/admin/`.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log

