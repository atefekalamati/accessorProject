# AUTH-09 — GET /api/v1/auth/me and PATCH /api/v1/users/me

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 2.5h (estimate) · **Deadline:** — · **Dependencies:** AUTH-06 · **Level:** HIGH

## Objective
دریافت کاربر جاری همراه نقش‌ها و permissionها، و تکمیل پروفایل.

## PRD reference
«هویت و دسترسی» ✓

## Acceptance Criteria
- [x] `GET /auth/me` پروفایل، نقش‌ها و permissionها را **از دیتابیس** برمی‌گرداند. بدون توکن → 401.
- [x] `PATCH /users/me` فقط `first_name`، `last_name` و `email` را می‌پذیرد. فیلدهای `role`، `status`، `mobile` یا هر فیلد سیستمی دیگر رد می‌شوند (schema با `extra="forbid"` → 400، طبق ADR-011).
- [x] نام خالی یا بیش از حد طولانی رد می‌شود.

## Implementation Notes
`app/modules/auth/`، یا ماژول `users` داخل `app/modules/auth/` (تصمیم در گام plan).

## Validation
```powershell
python -m pytest   # با TEST_DATABASE_URL
python -m mypy app tests
```

## Log
### 2026-10-09 — COMPLETE (batch AUTH-08/10/09)
- `GET /api/v1/auth/me` و `PATCH /api/v1/users/me` (یک `users_router` داخل ماژول auth). پاسخ `ProfileResponse` است: فیلد API `mobile` از ستون `phone` خوانده می‌شود و roles و permissions مرتب و از DB می‌آیند (AUTH-10).
- PATCH با `extra="forbid"` فقط `first_name`، `last_name` و `email` را می‌پذیرد. `mobile`، `phone`، `role`، `status`، `mobile_verified_at`، `verified`، `id` و هر فیلد دیگر → 400.
  - نام‌ها trim می‌شوند. خالی، `null` یا بیش از ۱۰۰ کاراکتر → 400.
  - email با `email-validator` (فقط syntax، `check_deliverability=False`)، trim و lowercase کامل نرمال می‌شود (حداکثر ۲۵۴). `null` ایمیل را پاک می‌کند.
  - فقط فیلدهای ارسال‌شده تغییر می‌کنند و ردیف user با `FOR UPDATE` قفل می‌شود.
- audit `user.profile_updated` فقط برای فیلدهایی که واقعاً تغییر کرده‌اند ثبت می‌شود. email در diff با `mask_email` ماسک می‌شود (`a***i@example.com`). PATCH بدون تغییر audit ندارد.
- `Cache-Control: no-store` روی verify-otp، refresh، logout، `/auth/me` و `/users/me` با یک تست واحد.
- dependency جدید: `email-validator>=2.3,<3.0` (دلیل: اعتبارسنجی استاندارد email؛ بدون DNS).
- تست‌ها: `tests/test_auth_me.py` (۳۴ مورد) و ۶ unit test برای `mask_email` در `tests/test_logging.py`.
- Validation: pytest 550 passed، ruff، format و mypy سبز.
### 2026-10-09 — FIX (درخواست کاربر پس از CI سبز)
- diff در audit حالا روی مقادیر خام ساخته می‌شود و بعد ماسک می‌شود (`record_audit(..., field_masks={"email": mask_email})`). هر ردیف diff `"changed": true` دارد، پس تغییر email حتی وقتی دو ماسک یکسان باشند هم دیده می‌شود. محدودیت ثبت‌شده در ADR-018 برطرف شد.
- این قرارداد در `app/shared/audit.py` (INF-05) برای همه actionها اعمال شد: هر ردیف diff `changed: true` دارد و ماسک phone هم دیگر باعث حذف تغییر نمی‌شود.
- تست‌ها: ۲ unit test در `tests/test_audit.py` و ۱ تست در `tests/test_auth_me.py`. pytest 553 passed، ruff، format و mypy سبز.
