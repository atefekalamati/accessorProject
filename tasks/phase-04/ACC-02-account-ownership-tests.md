# ACC-02 — Account ownership tests

**Status:** NOT_STARTED · **Priority:** HIGH · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** ACC-01 · **Level:** MEDIUM

## Objective
تست IDOR برای همه endpointهای مالکیت‌دار مشتری.

## PRD reference
«سفارش‌ها» ✓، «آدرس» ✓، «سبد خرید» ✓.

## Acceptance Criteria
- [ ] دو کاربر: سفارش، لغو، پرداخت، آدرس و خط سبد دیگری → 404 و بدون اثر جانبی.
- [ ] فهرست‌ها هیچ ردیفی از کاربر دیگر ندارند.

## Implementation Notes
فقط `tests/test_account_ownership.py`.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log

