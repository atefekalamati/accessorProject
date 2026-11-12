# OPS-10 — Provider contract tests (payment, SMS, storage)

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** PAY-01, AUTH-04, CAT-05 · **Level:** MEDIUM

## Objective
یک suite قرارداد مشترک که هر adapter درگاه، SMS و storage باید پاس کند؛ قفل رفتار fail-closed در production.

## PRD reference
ADR-009، ADR-049، ADR-058.

## Acceptance Criteria
- [x] storage: ذخیره، بازنویسی، حذف idempotent، URL ساخته سرور، رد کلید ساخته‌نشده.
- [x] SMS: ارسال بدون log کد یا موبایل کامل.
- [x] درگاه: reference معتبر، PAID فقط بعد از پرداخت با مبلغ گرفته‌شده، رد/ناشناخته هرگز PAID، callback امن.
- [x] production: درگاه و SMS ساخته نمی‌شوند، startup با job تطبیق شکست می‌خورد، storage حافظه‌ای رد می‌شود.

## Implementation Notes
`tests/test_provider_contracts.py`؛ adapter واقعی آینده فقط به فهرست `*_IMPLEMENTATIONS` اضافه می‌شود.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-11-13: تست قرارداد مشترک providerها: storage (Local، InMemory)، SMS (Fake) و درگاه (Fake) پشت یک suite؛ adapter واقعی آینده فقط به فهرست اضافه می‌شود؛ قفل fail-closed در production (درگاه و SMS ساخته نمی‌شوند، startup با job تطبیق شکست می‌خورد، storage حافظه‌ای رد می‌شود)؛ بدون تغییر کد برنامه، چون interface و fake از قبل بودند. COMPLETE.
