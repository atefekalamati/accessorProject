# FND-04 — Database layer + initial migration

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 6h (estimate) · **Deadline:** — · **Dependencies:** FND-01

## Objective
SQLAlchemy async، naming convention ثابت، migration اولیه جدول‌های پایه و تست constraintها.

## PRD reference
«معماری سیستم»، «هویت و دسترسی»

## Acceptance Criteria
- [x] engine و session async با timezone UTC (`app/db/session.py`).
- [x] migration `20260913_0001`: `users`، `roles`، `permissions`، `user_roles`، `role_permissions`، `addresses`، `audit_logs`، `app_settings`.
- [x] چرخه `upgrade → downgrade → upgrade` موفق است و `compare_metadata` تفاوتی نشان نمی‌دهد.
- [x] constraintها تست شده‌اند: `phone` یکتا، حداکثر یک آدرس پیش‌فرض، check روی status، و trigger ضدحذف `audit_logs`.

## Implementation Notes
`app/db/`، `alembic/`، `tests/test_database.py`.

## Validation
```powershell
$env:TEST_DATABASE_URL = "postgresql+asyncpg://postgres:test@localhost:55432/project_ak_test"
python -m pytest
```

## Log
- 2026-09-13: پیاده‌سازی شد (مرحله ۱ نقشه راه قدیمی).
- 2026-09-29: با PostgreSQL 16 موقت، ۲۴ تست پاس شدند. `alembic downgrade -1` و `upgrade head` موفق بودند.
