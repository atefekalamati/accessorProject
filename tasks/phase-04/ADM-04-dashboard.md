# ADM-04 — Dashboard metrics

**Status:** NOT_STARTED · **Priority:** MEDIUM · **Estimate:** 4h (estimate) · **Deadline:** — · **Dependencies:** ADM-01 · **Level:** HIGH

## Objective
`GET /admin/dashboard`.

## PRD reference
«داشبورد» ✓؛ ADR-047، D39.

## Acceptance Criteria
- [ ] شاخص‌های بخش «داشبورد» ✓ برای امروز، ۷ و ۳۰ روز به وقت `Asia/Tehran`.
- [ ] فروش موفق = `payment_status = paid`؛ اعداد صحیح تومان؛ تعداد query ثابت.
- [ ] مجوز `reports:read`؛ تست مرز روز تهران.

## Implementation Notes
ماژول جدید `app/modules/reports/`؛ تابع خالص بازه‌های تهران (unit test).

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log

