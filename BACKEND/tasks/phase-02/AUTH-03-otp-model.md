# AUTH-03 — OtpCode model (hashed, expiring, attempt-limited)

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** AUTH-01 · **Level:** HIGH

## Objective
مدل و migration برای کد OTP هش‌شده.

## PRD reference
«هویت و دسترسی» ✓ (Entity OtpCode)

## Acceptance Criteria
- [x] جدول `otp_codes` با ستون‌های `mobile`، `code_hash`، `expires_at`، `consumed_at`، `attempt_count`، `created_at`، `ip` ساخته شده و index روی `(mobile, created_at)` دارد.
- [x] کد OTP هرگز به‌صورت plaintext ذخیره نمی‌شود. **پیشنهاد:** HMAC-SHA256 با کلید سرور (نه SHA ساده)، چون فضای ۶ رقمی به‌راحتی brute-force می‌شود.
- [x] مدل در `app/db/models/__init__.py` export و به `_MODELS` در `alembic/env.py` اضافه شده است. `EXPECTED_TABLES` به‌روز شده است.
- [x] migration جدید، upgrade و downgrade سالم.

- [x] (اضافه در تأیید batch) `otp_codes.mobile` همان فرمت E.164 و CHECK را دارد که `users.phone` دارد.
- [x] (اضافه در تأیید batch) کلید HMAC یک setting جدا به اسم `OTP_HASH_SECRET` است (حداقل ۳۲ کاراکتر). مقدار پیش‌فرض تست در `conftest` است. در production نبودن آن startup را fail می‌کند. این‌ها تست دارند.

## Implementation Notes
`app/db/models/auth.py` (فایل جدید و برنامه‌ریزی‌شده)، `app/db/models/__init__.py`، `alembic/env.py`، `alembic/versions/`، `tests/test_database.py`.

## Validation
```powershell
python -m pytest   # با TEST_DATABASE_URL
python -m mypy app tests
```

## Log
- 2026-10-06: COMPLETE (batch AUTH-01/03/04).
  - مدل `OtpCode` در `app/db/models/auth.py` و migration `20261006_0003` ساخته شدند.
  - CHECKها: `mobile` با فرمت E.164، `code_hash ~ '^[0-9a-f]{64}$'` (ذخیره کد plaintext در دیتابیس ممکن نیست) و `attempt_count >= 0`.
  - indexها: `(mobile, created_at)` و `created_at` (از mixin؛ برای پاک‌سازی بعدی مفید است).
  - `app/modules/auth/otp.py` شامل `hash_otp_code` است: HMAC-SHA256 روی `"{mobile}:{code}"`، تا hash یک شماره برای شماره دیگر معتبر نباشد. همچنین `verify_otp_code` (با `compare_digest`) و `otp_hash_key(settings)` را دارد. `otp_hash_key` اگر کلید تنظیم نشده باشد خطا می‌دهد (fail-closed).
  - `Settings.otp_hash_secret` از نوع `SecretStr | None` با `min_length=32` است. در production اجباری است و بیرون از production اختیاری (استفاده بدون کلید fail-closed است). placeholder در `.env.example` اضافه شد.
  - **اقدام کاربر:** `OTP_HASH_SECRET` را در `.env` محلی بگذارید. بدون آن، AUTH-05 در dev خطا می‌دهد.
  - اعتبارسنجی: downgrade -1 و upgrade روی postgres-test؛ `compare_metadata` بدون تفاوت؛ pytest 393 passed؛ ruff، format و mypy سبز.
