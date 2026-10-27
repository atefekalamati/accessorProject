# ADM-04 — Dashboard metrics

**Status:** COMPLETE · **Priority:** MEDIUM · **Estimate:** 4h (estimate) · **Deadline:** — · **Dependencies:** ADM-01 · **Level:** HIGH

## Objective
`GET /admin/dashboard`.

## PRD reference
«داشبورد» ✓؛ ADR-047، D39.

## Acceptance Criteria
- [x] شاخص‌های بخش «داشبورد» ✓ برای امروز، ۷ و ۳۰ روز به وقت `Asia/Tehran`.
- [x] فروش موفق = `payment_status = paid`؛ اعداد صحیح تومان؛ تعداد query ثابت.
- [x] مجوز `reports:read`؛ تست مرز روز تهران.

## Implementation Notes
ماژول جدید `app/modules/reports/`؛ تابع خالص بازه‌های تهران (unit test).

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-10-26: پیاده‌سازی (batch 4، ADR-055).
  - ماژول جدید `app/modules/reports/`؛ `GET /admin/dashboard` با `reports:read` و `no-store`؛ چهار query ثابت.
  - مرز روز تهران در PostgreSQL (`tzdata` روی Windows نیست)؛ تابع خالص: میانگین floor و offset روزها. تست مرز با نیمه‌شب تهران (20:30 UTC).
  - `stock_columns` در `inventory/admin_repository.py` عمومی شد.
  - بازبینی opus: بدون blocker. رفع شد: HAVING روی اولین `paid_at`، تست سفارش با دو payment موفق، توضیح فیلتر تنوع فعال و مشتری حذف‌شده.
  - Level HIGH. COMPLETE.
