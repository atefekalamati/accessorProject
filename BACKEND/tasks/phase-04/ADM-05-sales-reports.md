# ADM-05 — Sales reports

**Status:** COMPLETE · **Priority:** MEDIUM · **Estimate:** 4h (estimate) · **Deadline:** — · **Dependencies:** ADM-04 · **Level:** HIGH

## Objective
گزارش‌های فروش زمانی، محصول و دسته.

## PRD reference
«گزارش‌ها» ✓؛ D39.

## Acceptance Criteria
- [x] `/admin/reports/sales` با `group_by` day/week/month (تهران)، بازه ≤ ۳۶۶ روز.
- [x] `/admin/reports/products` و `/categories` از snapshot خطوط.
- [x] جمع گروه‌ها = جمع کل؛ اعداد صحیح؛ فقط فروش موفق (مبنای `paid_at`).

## Implementation Notes
`app/modules/reports/`.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-10-27: پیاده‌سازی (batch 4، ADR-055).
  - `GET /admin/reports/sales` (`group_by` day/week/month)، `/products` (`limit` 1..100، پیش‌فرض 20) و `/categories`؛ `reports:read` و `no-store`.
  - تصمیم کاربر: هفته از شنبه و ماه جلالی. جمع روزانه به تاریخ تهران در SQL؛ rollup در Python با `to_jalali` خالص (`app/modules/reports/calendar.py`) و تست پیوستگی روزبه‌روز 2019–2033.
  - `from`/`to` تاریخ تهران، بازه نیمه‌باز، حداکثر ۳۶۶ روز؛ bucketها با `label` جلالی، `starts_on` و `ends_before` (برش به بازه) و bucket خالی هم برمی‌گردد.
  - دسته = دسته فعلی محصول (خط snapshot دسته ندارد)؛ عنوان = آخرین snapshot؛ totals شامل گروه‌های بعد از `limit`.
  - بازبینی opus: بدون blocker. رفع شد: overflow در `date.max`، tiebreaker عنوان، فیلتر `until` در subquery پرداخت، نوع `Sequence` در تست.
  - Level HIGH. COMPLETE.
