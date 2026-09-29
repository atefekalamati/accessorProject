# FND-07 — CI pipeline

**Status:** NOT_STARTED · **Priority:** MEDIUM · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** FND-06، ADR-013 (GitHub Actions تأیید شد)

## Objective
هر push و PR به‌صورت خودکار با lint، type-check و تست کامل (با PostgreSQL) بررسی شود.

## PRD reference
«تست و پذیرش» (قالبی)

## Acceptance Criteria
- [ ] `.github/workflows/ci.yml` روی `ubuntu-latest` با Python 3.12 و `pip install -e ".[dev]"` اجرا می‌شود.
- [ ] service container `postgres:16-alpine` با دیتابیس `project_ak_test` دارد.
- [ ] این گام‌ها را اجرا می‌کند: `ruff check .`، `ruff format --check .`، `mypy app tests`، `pytest` با `TEST_DATABASE_URL`.
- [ ] workflow روی شاخه سبز است. push فقط با درخواست کاربر انجام می‌شود.

## Implementation Notes
`.github/workflows/ci.yml` (فایل جدید و برنامه‌ریزی‌شده). repo روی GitHub در `atefekalamati/accessorProject` است.

## Validation
اجرای workflow روی GitHub.

## Log
- 2026-09-29: از `tasks/M0-03-ci-pipeline.md` منتقل شد.
