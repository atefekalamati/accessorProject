# FND-07 — CI pipeline

**Status:** COMPLETE · **Priority:** MEDIUM · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** FND-06، ADR-013 (GitHub Actions تأیید شد) · **Level:** LOW

## Objective
هر push و PR به‌صورت خودکار با lint، type-check و تست کامل (با PostgreSQL) بررسی شود.

## PRD reference
«تست و پذیرش» (قالبی)

## Acceptance Criteria
- [x] `.github/workflows/ci.yml` روی `ubuntu-latest` با Python 3.12 و `pip install -e ".[dev]"` اجرا می‌شود.
- [x] service container `postgres:16-alpine` با دیتابیس `project_ak_test` دارد.
- [x] این گام‌ها را اجرا می‌کند: `ruff check .`، `ruff format --check .`، `mypy app tests`، `pytest` با `TEST_DATABASE_URL`.
- [x] (اضافه‌شده در plan) اگر حتی یک تست skip شود، workflow fail می‌شود (از روی junit XML).
- [x] (اضافه‌شده در plan) `permissions: contents: read`؛ trigger روی push همه شاخه‌ها و pull_request فقط به `master`؛ actionها روی نسخه major pin شده‌اند.
- [x] workflow روی شاخه سبز است. push فقط با درخواست کاربر انجام می‌شود.

## Implementation Notes
`.github/workflows/ci.yml`. repo روی GitHub در `atefekalamati/accessorProject` است.
- `concurrency` اجرای قدیمی‌ترِ همان ref را لغو می‌کند؛ `timeout-minutes: 15`.
- `DATABASE_URL` و `JWT_SECRET` را `tests/conftest.py` با `setdefault` پر می‌کند؛ در workflow فقط `TEST_DATABASE_URL` لازم است.

## Validation
- محلی (2026-09-29): `pytest` با `postgres-test` → 284 passed، 0 skipped. `ruff check`، `ruff format --check`، `mypy app tests` سبز. اسکریپت ضد-skip: با DB → exit 0؛ بدون DB → 10 skip و exit 1.
- GitHub: اجرای Actions برای commit `8c7bf9b` سبز شد (تأیید کاربر، 2026-09-29).

## Log
- 2026-09-29: از `tasks/M0-03-ci-pipeline.md` منتقل شد.
- 2026-09-29: workflow نوشته و محلی بررسی شد؛ مرحله ۱ `/done` (push). منتظر نتیجه Actions.
- 2026-09-29: CI روی GitHub سبز شد؛ COMPLETE.
