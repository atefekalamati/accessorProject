# AUTH-01 — Align User model with PRD + migration

**Status:** NOT_STARTED · **Priority:** HIGH · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** FND-04, ADR-003 · **Level:** HIGH

## Objective
جدول `users` از قبل موجود است (`phone`، `status`، `full_name`، `deleted_at`). این task آن را با فیلدهای PRD هماهنگ می‌کند: `first_name`، `last_name`، `email` (اختیاری) و `mobile_verified_at`.

## PRD reference
«هویت و دسترسی» ✓ (Entity User)

## Acceptance Criteria
- [ ] migration **جدید** (`--rev-id YYYYMMDD_0002`) ساخته شده است. migration `20260913_0001` ویرایش نمی‌شود.
- [ ] `full_name` با `first_name` و `last_name` جایگزین شده است (نام نباید خالی یا بیش از حد طولانی باشد؛ CheckConstraint). **پیشنهاد:** چون داده production وجود ندارد، مهاجرت داده لازم نیست.
- [ ] فیلد `email` nullable و `mobile_verified_at` از نوع timezone-aware است.
- [ ] قانون «هر شماره موبایل فقط به یک حساب فعال» رعایت می‌شود. طبق ADR-015، `uq_users_phone` به partial unique index با شرط `WHERE deleted_at IS NULL` تبدیل می‌شود. استثنا فقط با دلیل ثبت‌شده در plan پذیرفته است.
- [ ] upgrade، downgrade و upgrade موفق است و `compare_metadata` تفاوتی نشان نمی‌دهد.
- [ ] `docs/dbeaver.md` به‌روز شده است.

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
