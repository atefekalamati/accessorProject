# FND-03 — Docker/Compose runnable end-to-end

**Status:** IN_PROGRESS · **Priority:** HIGH · **Estimate:** 3h (estimate؛ ~1h باقی) · **Deadline:** — · **Dependencies:** FND-01, FND-04

## Objective
مسیر مستند README (`.env` → `docker compose up --build`) واقعاً کار کند: API و PostgreSQL سالم، migration و seed داخل container.

## PRD reference
«معماری سیستم»

## Acceptance Criteria
- [x] `Dockerfile` کاربر non-root دارد و `docker build` موفق است (2026-09-29).
- [x] `docker compose config` معتبر است (2026-09-29).
- [ ] `.env` محلی از `.env.example` ساخته شده و `JWT_SECRET` و `POSTGRES_PASSWORD` مقدار محلی دارند (secret در گزارش یا git نمی‌آید).
- [ ] `docker compose up --build -d` هر دو سرویس را healthy بالا می‌آورد (پورت‌های 5432 و 8000 آزاد باشند).
- [ ] `alembic upgrade head` و `python -m app.db.seed` داخل container `api` اجرا می‌شوند.
- [ ] `/health`، `/ready` و `/docs` از طریق compose پاسخ 200 می‌دهند.
- [ ] اگر شکافی پیدا شد، README به‌روز شود. پایان کار با `docker compose down` (بدون `-v`).

## Implementation Notes
`.env` (محلی، gitignored)، `docker-compose.yml`، `Dockerfile`، `README.md`.
باید بررسی شود که `alembic.ini` و `alembic/` در image کپی می‌شوند (کپی می‌شوند) و `alembic` از dependencies نصب است.

## Validation
```powershell
docker compose up --build -d
docker compose exec api alembic upgrade head
docker compose exec api python -m app.db.seed
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/ready
docker compose down
```

## Log
- 2026-09-29: از `tasks/M0-01-local-env-verification.md` منتقل شد. build و config موفق بودند. `up` به دلیل نبود `.env` اجرا نشد.
