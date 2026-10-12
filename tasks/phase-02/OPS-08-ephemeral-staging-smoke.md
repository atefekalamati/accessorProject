# OPS-08 — Ephemeral staging smoke in CI

**Status:** COMPLETE · **Priority:** MEDIUM · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** FND-03, FND-07 · **Level:** MEDIUM

## Objective
یک job در CI که image را از Dockerfile می‌سازد، stack را با docker compose روی دیتابیس خالی بالا می‌آورد، `alembic upgrade head` و seed را اجرا می‌کند و smoke انجام می‌دهد: health/ready، ورود OTP با SMS جعلی، خواندن کاتالوگ و یک نوشتن ادمین. هر شکست PR را قرمز می‌کند (ADR-037).

## PRD reference
ADR-037 (دروازه فاز)؛ ADR-009 (provider جعلی)؛ ADR-013 (دیتابیس یک‌بارمصرف).

## Plan (batch OPS-08/OPS-09)
- `scripts/smoke.py` (فقط stdlib، `urllib`؛ بدون dependency جدید): دو مرحله.
  - `login`: انتظار health (`/api/v1/health`، با retry تا ۶۰s) و ready (`/api/v1/ready`)؛ `POST /auth/request-otp` و `POST /auth/verify-otp` با کد mock؛ `GET /categories` = 200؛ `POST /admin/categories` با token مشتری = 403؛ token در فایل (`--token-file`، زیر `RUNNER_TEMP`).
  - `admin`: با همان token (مجوز هر درخواست از DB خوانده می‌شود، ADR-018) `POST /admin/categories` = 201 و `GET /categories/{slug}` = 200.
  - هر شکست → exit 1 با پیام مرحله؛ token هرگز چاپ نمی‌شود.
- `.github/workflows/ci.yml` job جدید `staging-smoke` (موازی با `checks`؛ روی PR به master، push به `master` و شاخه‌های `feat/phase-*`):
  1. ساخت `.env.staging` در runner با `ENVIRONMENT=staging`، secretهای تصادفی (`openssl rand`)، `OTP_MOCK_ENABLED=true`، `RESERVATION_SWEEP_SECONDS=0`، `MEDIA_STORAGE=memory`؛ هیچ secret واقعی و چیزی commit نمی‌شود.
  2. `docker compose --env-file .env.staging up -d --build --wait` با `APP_ENV_FILE=.env.staging` (volume تازه، پس دیتابیس خالی).
  3. `docker compose exec -T api alembic upgrade head` و `python -m app.db.seed`.
  4. `smoke.py login` → ارتقای کاربر smoke به super_admin با `psql` در کانتینر postgres → `smoke.py admin`.
  5. شکست: `docker compose logs`؛ همیشه: `docker compose down -v` (فقط runner یک‌بارمصرف CI).
- ریسک‌ها: کندی CI (build با cache لایه‌ای pip؛ هدف < 5 دقیقه)؛ flaky بودن شروع API (retry health)؛ نشت secret (تصادفی و فقط در runner، `--redact` gitleaks روی history اثری ندارد چون commit نمی‌شود)؛ cooldown OTP (فقط یک ورود).
- Rollback: حذف job؛ `git revert`.

## Acceptance Criteria
- [x] job `staging-smoke` image را می‌سازد، migration و seed را روی دیتابیس خالی اجرا می‌کند و هر چهار smoke را پاس می‌کند (CI سبز روی شاخه فاز).
- [x] شکست هر مرحله job را قرمز می‌کند (exit code غیرصفر؛ بررسی محلی با URL اشتباه).
- [x] هیچ secret واقعی یا فایل env در repo نیست؛ مجوز job `contents: read`.
- [x] ruff، format و mypy سبز (اسکریپت در `scripts/` تحت ruff است).

## Implementation Notes
- `scripts/smoke.py` (stdlib، دو مرحله `login`/`admin`)؛ job `staging-smoke` در `.github/workflows/ci.yml` با project جدای compose (`-p project-ak-staging`) تا هرگز container یا volume یک stack dev را شریک نشود؛ `.env.staging` در `.gitignore`.
- اجرای محلی کامل (پورت‌های 8011/55440): build، migration، seed، شش smoke `login`، 403 قبل از ارتقا، ارتقا با psql، دو smoke `admin` سبز؛ URL غیرقابل‌دسترس → exit 1. volume محلی `project-ak-staging_postgres_data` باقی ماند (حذف با `down -v` نیازمند تأیید کاربر است).
- **Rollback:** حذف job و اسکریپت؛ `git revert`.

## Validation
```powershell
python -m ruff check .; python -m ruff format --check .; python -m mypy app tests
# محلی: docker compose بالا، سپس
python scripts/smoke.py login --base-url http://127.0.0.1:8000 --mobile +989120000001 --token-file $env:TEMP\smoke-token
```

## Log
- 2026-10-12: فایل task و plan (batch OPS-08/OPS-09، AUTOPILOT؛ GHCR در ADR-037 تأیید کاربر).
- 2026-10-12: commit `71534d9`؛ CI run 38304563875 سبز (staging-smoke در 42s: build، migration، seed، smoke login، ارتقا، smoke admin). ruff، format و mypy سبز. COMPLETE.
