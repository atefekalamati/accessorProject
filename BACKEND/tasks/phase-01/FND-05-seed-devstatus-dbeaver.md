# FND-05 — Role seed, dev DB-status route, DBeaver doc

**Status:** COMPLETE · **Priority:** MEDIUM · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** FND-04 · **Level:** LOW

## Objective
seed idempotent نقش‌ها، endpoint وضعیت دیتابیس فقط برای development و راهنمای DBeaver.

## PRD reference
«هویت و دسترسی»

## Acceptance Criteria
- [x] `python -m app.db.seed` idempotent است (`test_role_seed_is_idempotent`).
- [x] `/api/v1/dev/database-status` در production وجود ندارد (`test_development_database_status_is_absent_in_production`).
- [x] `docs/dbeaver.md` نوشته شده است.

## Implementation Notes
`app/db/seed.py`، `app/shared/database/`، `docs/dbeaver.md`. مجموعه نهایی نقش‌ها به D2 وابسته است و در AUTH-02 تکمیل می‌شود.

## Validation
```powershell
python -m pytest tests/test_database.py tests/test_database_routes.py
```

## Log
- 2026-09-13: پیاده‌سازی شد.
- 2026-09-29: تأیید شد. seed روی دیتابیس موقت موفق بود.
