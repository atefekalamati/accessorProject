# FND-06 — Reproducible test database recipe

**Status:** COMPLETE (2026-09-29) · **Priority:** MEDIUM · **Estimate:** 1.5h (estimate) · **Deadline:** — · **Dependencies:** FND-04, ADR-013 · **Level:** LOW

## Objective
اجرای تست‌های integration به ساخت دستی دیتابیس وابسته نباشد. تست‌ها کل schema را downgrade می‌کنند، پس دیتابیس تست باید جدا از دیتابیس توسعه باشد.

## PRD reference
«تست و پذیرش» (قالبی)

## Acceptance Criteria
- [x] سرویس `postgres-test` در `docker-compose.yml` با `profiles: ["test"]`، روی `127.0.0.1:55432` و بدون volume (ADR-013). `docker compose up` معمولی آن را بالا نمی‌آورد.
- [x] یک دستور مستند، دیتابیس تست را بالا می‌آورد. با `TEST_DATABASE_URL` همه تست‌ها سبز هستند.
- [x] دیتابیس توسعه و volume `postgres_data` دست‌نخورده می‌مانند.
- [x] بخش دستورات در CLAUDE.md با روش نهایی هماهنگ است.

## Implementation Notes
`docker-compose.yml`، `README.md`، `CLAUDE.md`.
افزوده‌های تأییدشده کاربر: پورت host قابل تنظیم با `${TEST_DB_HOST_PORT:-55432}` (در `.env.example`)، و guard در `tests/conftest.py` که اگر نام دیتابیس در `TEST_DATABASE_URL` با `_test` تمام نشود، کل session را abort می‌کند (exit 3). تست guard در `tests/test_database_guard.py` است.

## Validation
```powershell
python -m pytest   # با TEST_DATABASE_URL
```

## Log
- 2026-09-29: از `tasks/M0-02-test-database-recipe.md` منتقل شد. دستور `docker run` روی پورت 55432 همان روز تأیید شد.
- 2026-09-29: COMPLETE. سرویس `postgres-test` (profile `test`، پورت `127.0.0.1:${TEST_DB_HOST_PORT:-55432}`، بدون volume، با healthcheck). `docker compose config --services` بدون profile شامل آن نیست. guard در `pytest_sessionstart`؛ fixture `database_url` در `test_database.py` فقط skip می‌کند. README و CLAUDE.md به دستور compose تغییر کردند. pytest 284 passed (بدون skip) روی `postgres-test`؛ ruff، format و mypy سبز؛ volume `atk_postgres_data` دست‌نخورده ماند.
