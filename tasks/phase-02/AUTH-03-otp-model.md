# AUTH-03 — OtpCode model (hashed, expiring, attempt-limited)

**Status:** NOT_STARTED · **Priority:** HIGH · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** AUTH-01

## Objective
مدل و migration برای کد OTP هش‌شده.

## PRD reference
«هویت و دسترسی» ✓ (Entity OtpCode)

## Acceptance Criteria
- [ ] جدول `otp_codes` با ستون‌های `mobile`، `code_hash`، `expires_at`، `consumed_at`، `attempt_count`، `created_at`، `ip` ساخته شده و index روی `(mobile, created_at)` دارد.
- [ ] کد OTP هرگز به‌صورت plaintext ذخیره نمی‌شود. **پیشنهاد:** HMAC-SHA256 با کلید سرور (نه SHA ساده)، چون فضای ۶ رقمی به‌راحتی brute-force می‌شود.
- [ ] مدل در `app/db/models/__init__.py` export و به `_MODELS` در `alembic/env.py` اضافه شده است. `EXPECTED_TABLES` به‌روز شده است.
- [ ] migration جدید، upgrade و downgrade سالم.

## Implementation Notes
`app/db/models/auth.py` (فایل جدید و برنامه‌ریزی‌شده)، `app/db/models/__init__.py`، `alembic/env.py`، `alembic/versions/`، `tests/test_database.py`.

## Validation
```powershell
python -m pytest   # با TEST_DATABASE_URL
python -m mypy app tests
```

## Log
