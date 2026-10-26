# ADM-05 — Sales reports

**Status:** NOT_STARTED · **Priority:** MEDIUM · **Estimate:** 4h (estimate) · **Deadline:** — · **Dependencies:** ADM-04 · **Level:** HIGH

## Objective
گزارش‌های فروش زمانی، محصول و دسته.

## PRD reference
«گزارش‌ها» ✓؛ D39.

## Acceptance Criteria
- [ ] `/admin/reports/sales` با `group_by` day/week/month (تهران)، بازه ≤ ۳۶۶ روز.
- [ ] `/admin/reports/products` و `/categories` از snapshot خطوط.
- [ ] جمع گروه‌ها = جمع کل؛ اعداد صحیح؛ فقط فروش موفق (مبنای `paid_at`).

## Implementation Notes
`app/modules/reports/`.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log

