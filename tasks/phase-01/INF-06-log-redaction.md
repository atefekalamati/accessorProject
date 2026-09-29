# INF-06 — Sensitive-data redaction in logs

**Status:** NOT_STARTED · **Priority:** MEDIUM · **Estimate:** 1.5h (estimate) · **Deadline:** — · **Dependencies:** FND-02 · **Level:** HIGH

## Objective
قبل از شروع auth، مطمئن شویم کد OTP، token و هدر `Authorization` هرگز در log نمی‌آیند و شماره موبایل mask می‌شود.

## PRD reference
«امنیت» (قالبی)، «هویت و دسترسی» ✓

## Acceptance Criteria
- [ ] `JsonFormatter` کلیدهای حساس (`otp`، `code`، `token`، `refresh_token`، `authorization`، `password`) را با `***` جایگزین می‌کند.
- [ ] شماره موبایل در log به شکل `+98912***4567` mask می‌شود.
- [ ] تست با `caplog` نشان می‌دهد مقدار حساس در خروجی نیست.

## Implementation Notes
`app/core/logging.py` و `tests/test_logging.py` (فایل جدید و برنامه‌ریزی‌شده).

## Validation
```powershell
python -m pytest tests/test_logging.py
python -m mypy app tests
```

## Log
