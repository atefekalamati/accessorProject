# AUTH-01 — Align User model with PRD + migration

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** FND-04, ADR-003 · **Level:** HIGH

## Objective
جدول `users` از قبل موجود است (`phone`، `status`، `full_name`، `deleted_at`). این task آن را با فیلدهای PRD هماهنگ می‌کند: `first_name`، `last_name`، `email` (اختیاری) و `mobile_verified_at`.

## PRD reference
«هویت و دسترسی» ✓ (Entity User)

## Acceptance Criteria
- [x] migration **جدید** (`--rev-id YYYYMMDD_0002`) ساخته شده است. migration `20260913_0001` ویرایش نمی‌شود.
- [x] `full_name` با `first_name` و `last_name` جایگزین شده است (نام نباید خالی یا بیش از حد طولانی باشد؛ CheckConstraint). **پیشنهاد:** چون داده production وجود ندارد، مهاجرت داده لازم نیست.
- [x] فیلد `email` nullable و `mobile_verified_at` از نوع timezone-aware است.
- [x] قانون «هر شماره موبایل فقط به یک حساب فعال» رعایت می‌شود. طبق ADR-015، `uq_users_phone` به partial unique index با شرط `WHERE deleted_at IS NULL` تبدیل می‌شود. استثنا فقط با دلیل ثبت‌شده در plan پذیرفته است.
- [x] نام ستون دیتابیس `phone` می‌ماند. نام فیلدهای API از PRD پیروی می‌کند (`mobile`)، و نگاشت آن در schemaهای Pydantic انجام می‌شود.
- [x] upgrade، downgrade و upgrade موفق است و `compare_metadata` تفاوتی نشان نمی‌دهد.
- [x] `docs/dbeaver.md` به‌روز شده است.

- [x] (اضافه در تأیید batch) `phone` فقط به شکل E.164 نرمال‌شده (`+989XXXXXXXXX`) ذخیره می‌شود و CHECK دیتابیسی `ck_users_phone_format` دارد. `normalize_phone()` در `app/core/phone.py` ورودی‌های `09…`، `+98…`، `0098…` و ارقام فارسی و عربی را می‌پذیرد و unit test دارد. AUTH-05 و AUTH-09 از آن استفاده می‌کنند.

## Implementation Notes
`app/db/models/users.py`، `alembic/versions/` (migration جدید)، `tests/test_database.py` (assertion روی revision و ستون‌ها)، `docs/dbeaver.md`.

## Validation
```powershell
alembic upgrade head; alembic downgrade -1; alembic upgrade head
python -m pytest   # با TEST_DATABASE_URL
python -m ruff check .
python -m ruff format --check .
python -m mypy app tests
```

## Log
- 2026-10-06: COMPLETE (batch AUTH-01/03/04).
  - migration `20261006_0002`: `full_name` حذف شد. `first_name` و `last_name` (`String(100)`، nullable، CHECK غیرخالی)، `email` (`String(254)`، nullable، بدون unique طبق Q1) و `mobile_verified_at` (timestamptz) اضافه شدند. `uq_users_phone` به partial unique index با شرط `deleted_at IS NULL` تبدیل شد. `ck_users_phone_not_blank` با `ck_users_phone_format` جایگزین شد.
  - نام‌ها nullable هستند، چون کاربری که تازه با OTP وارد شده هنوز نام ندارد.
  - downgrade، `full_name` و unique کامل را برمی‌گرداند. داده نام و ایمیل از دست می‌رود. اگر کاربر soft-deleted با موبایل تکراری وجود داشته باشد، downgrade fail می‌شود.
  - **نکته برای دیتابیس توسعه:** اگر `users` ردیفی با موبایل غیر E.164 داشته باشد، upgrade روی CHECK fail می‌شود. upgrade روی دیتابیس توسعه اجرا نشد.
  - اعتبارسنجی: چرخه upgrade → downgrade -1 → upgrade روی postgres-test؛ `compare_metadata` بدون تفاوت؛ pytest 374 passed؛ ruff، format و mypy سبز.
