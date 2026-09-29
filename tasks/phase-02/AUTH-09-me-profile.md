# AUTH-09 — GET /api/v1/auth/me and PATCH /api/v1/users/me

**Status:** NOT_STARTED · **Priority:** HIGH · **Estimate:** 2.5h (estimate) · **Deadline:** — · **Dependencies:** AUTH-06 · **Level:** HIGH

## Objective
دریافت کاربر جاری همراه نقش‌ها و permissionها، و تکمیل پروفایل.

## PRD reference
«هویت و دسترسی» ✓

## Acceptance Criteria
- [ ] `GET /auth/me` پروفایل، نقش‌ها و permissionها را **از دیتابیس** برمی‌گرداند. بدون توکن → 401.
- [ ] `PATCH /users/me` فقط `first_name`، `last_name` و `email` را می‌پذیرد. فیلدهای `role`، `status`، `mobile` یا هر فیلد سیستمی دیگر رد می‌شوند (schema با `extra="forbid"` → 400، طبق ADR-011).
- [ ] نام خالی یا بیش از حد طولانی رد می‌شود.

## Implementation Notes
`app/modules/auth/`، یا ماژول `users` داخل `app/modules/auth/` (تصمیم در گام plan).

## Validation
```powershell
python -m pytest   # با TEST_DATABASE_URL
python -m mypy app tests
```

## Log
