# INF-06 — Sensitive-data redaction in logs

**Status:** COMPLETE · **Priority:** MEDIUM · **Estimate:** 1.5h (estimate) · **Deadline:** — · **Dependencies:** FND-02 · **Level:** HIGH

## Objective
قبل از شروع auth، مطمئن شویم کد OTP، token و هدر `Authorization` هرگز در log نمی‌آیند و شماره موبایل mask می‌شود.

## PRD reference
«امنیت» (قالبی)، «هویت و دسترسی» ✓

## Acceptance Criteria
- [x] `JsonFormatter` کلیدهای حساس (`otp`، `code`، `token`، `refresh_token`، `authorization`، `password`) را با `***` جایگزین می‌کند.
- [x] شماره موبایل در log به شکل `+98912***4567` mask می‌شود.
- [x] تست با `caplog` نشان می‌دهد مقدار حساس در خروجی نیست.

## Implementation Notes
`app/core/logging.py` و `tests/test_logging.py` (فایل جدید و برنامه‌ریزی‌شده).
- helper مشترک در `app/core/redaction.py` (`redact`، `mask_text`، `mask_phone`، `is_sensitive_key`) که INF-05 از آن استفاده می‌کند.
- تغییرهای تأییدشده کاربر نسبت به plan:
  - کلیدها با substring و case-insensitive پیدا می‌شوند: `token`، `secret`، `password`، `otp`، `authorization`، `cookie`، `api_key`.
  - `code` فقط وقتی مقدارش ۴ تا ۸ رقم است redact می‌شود.
  - Bearer و JWT بر اساس خود مقدار در message، extras و traceback mask می‌شوند.
  - رقم فارسی و عربی هم پوشش داده می‌شود.
  - formatter هرگز خطا نمی‌دهد و در صورت خطا `log.redaction_failed` را ثبت می‌کند.
- قاعده phone ترجیحاً بیش از حد mask می‌کند: فقط رقم مجاور مانع mask می‌شود، و حرف، `-` یا `_` مجاور مانع نیست. به همین دلیل معیاری به ORD-01 اضافه شد: شماره سفارش شبیه موبایل نباشد.

## Validation
```powershell
python -m pytest tests/test_logging.py
python -m mypy app tests
```

## Log
- 2026-09-29: COMPLETE. pytest 327 passed و 0 skipped (postgres-test)؛ ruff، format و mypy سبز.
