# FND-06 — Reproducible test database recipe

**Status:** NOT_STARTED · **Priority:** MEDIUM · **Estimate:** 1.5h (estimate) · **Deadline:** — · **Dependencies:** FND-04, ADR-013

## Objective
اجرای تست‌های integration به ساخت دستی دیتابیس وابسته نباشد. تست‌ها کل schema را downgrade می‌کنند، پس دیتابیس تست باید جدا از دیتابیس توسعه باشد.

## PRD reference
«تست و پذیرش» (قالبی)

## Acceptance Criteria
- [ ] سرویس `postgres-test` در `docker-compose.yml` با `profiles: ["test"]`، روی `127.0.0.1:55432` و بدون volume (ADR-013). `docker compose up` معمولی آن را بالا نمی‌آورد.
- [ ] یک دستور مستند، دیتابیس تست را بالا می‌آورد. با `TEST_DATABASE_URL` همه تست‌ها سبز هستند.
- [ ] دیتابیس توسعه و volume `postgres_data` دست‌نخورده می‌مانند.
- [ ] بخش دستورات در CLAUDE.md با روش نهایی هماهنگ است.

## Implementation Notes
`docker-compose.yml`، `README.md`، `CLAUDE.md`.

## Validation
```powershell
python -m pytest   # با TEST_DATABASE_URL
```

## Log
- 2026-09-29: از `tasks/M0-02-test-database-recipe.md` منتقل شد. دستور `docker run` روی پورت 55432 همان روز تأیید شد.
