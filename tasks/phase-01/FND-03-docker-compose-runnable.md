# FND-03 — Docker/Compose runnable end-to-end

**Status:** IN_PROGRESS · **Priority:** HIGH · **Estimate:** 3h (estimate؛ ~1h باقی) · **Deadline:** — · **Dependencies:** FND-01, FND-04

## Objective
مسیر مستند README (`.env` → `docker compose up --build`) واقعاً کار کند: API و PostgreSQL سالم، migration و seed داخل container.

## PRD reference
«معماری سیستم»

## Acceptance Criteria
- [x] `Dockerfile` کاربر non-root دارد و `docker build` موفق است (2026-09-29).
- [x] `docker compose config` معتبر است (2026-09-29).
- [x] پورت‌های host در compose قابل تنظیم‌اند: `${DB_HOST_PORT:-5432}` و `${API_HOST_PORT:-8000}`. `.env.example`، README و `docs/dbeaver.md` به‌روز شدند.
- [x] `.env` محلی ساخته شد: secretهای تصادفی، `DB_HOST_PORT=5435`، `API_HOST_PORT=8001`، و `DATABASE_URL` سمت host روی `localhost:5435`. در git ignore است.
- [x] سرویس `postgres` در compose healthy است (`127.0.0.1:5435`). `alembic upgrade head` و seed (دو بار) از host موفق بودند.
- [x] هر ۲۴ تست، شامل integration روی دیتابیس تست موقت (55432)، پاس شدند. ruff، format و mypy سبز بودند.
- [ ] `docker compose up --build -d` هر دو سرویس را healthy بالا می‌آورد. **مانع:** build ایمیج api به‌خاطر شبکه ناپایدار PyPI شکست می‌خورد.
- [ ] `alembic upgrade head` و `python -m app.db.seed` داخل container `api` اجرا می‌شوند.
- [ ] `/health`، `/ready` و `/docs` از طریق compose (پورت 8001) پاسخ 200 می‌دهند.
- [x] README به‌روز شد. پایان کار با `docker compose down` (بدون `-v`)؛ volume `atk_postgres_data` حفظ شد.

## Implementation Notes
`.env` (محلی، gitignored)، `docker-compose.yml`، `Dockerfile`، `README.md`.
باید بررسی شود که `alembic.ini` و `alembic/` در image کپی می‌شوند (کپی می‌شوند) و `alembic` از dependencies نصب است.

## Validation
```powershell
docker compose up --build -d
docker compose exec api alembic upgrade head
docker compose exec api python -m app.db.seed
Invoke-RestMethod http://localhost:8001/health   # API_HOST_PORT
Invoke-RestMethod http://localhost:8001/ready
docker compose down
```

## Log
- 2026-09-29: از `tasks/M0-01-local-env-verification.md` منتقل شد. build و config موفق بودند. `up` به دلیل نبود `.env` اجرا نشد.
- 2026-09-29: متوقف شد، چون پورت‌ها اشغال‌اند: 5432 (PostgreSQL محلی روی host، pid 6756) و 8000 (`wslrelay`، یعنی سرویسی داخل WSL). طبق دستور کاربر چیزی kill نشد. `.env` و container ساخته نشد.
  - گزینه‌ها: (۱) کاربر سرویس‌های اشغال‌کننده را خودش متوقف کند؛ (۲) پیشنهاد: پورت‌های host در `docker-compose.yml` قابل تنظیم شوند، مثلاً `127.0.0.1:${POSTGRES_HOST_PORT:-5432}:5432` و `${API_HOST_PORT:-8000}:8000`، و در `.env` مقدارهای 5433 و 8001 گذاشته شوند (تغییر کوچک، نیاز به تأیید).
- 2026-09-29: کاربر گزینه (۲) را با نام‌های `DB_HOST_PORT` و `API_HOST_PORT` تأیید کرد. پیاده‌سازی شد و `docker compose config` پورت‌های 5433 و 8001 را نشان داد. **دوباره متوقف شد:** 5433 را یک container دیگر Docker (`com.docker.backend`) اشغال کرده و 5434 هم اشغال است. 5435 و 15432 آزادند. 8001 آزاد است. منتظر انتخاب پورت دیتابیس توسط کاربر.
- 2026-09-29: کاربر 5435 را انتخاب کرد. build ایمیج api سه بار شکست خورد:
  1. `ReadTimeoutError` به `files.pythonhosted.org`.
  2. `ResolutionImpossible` بعد از ۱۶ دقیقه، به‌خاطر ناقص رسیدن index. تست از داخل container: صفحه `pydantic-core` با `IncompleteRead` قطع شد.
  3. hash mismatch، یعنی فایل‌های دانلودی ناقص بودند و pip درست آن‌ها را رد کرد.
  - `PIP_DEFAULT_TIMEOUT=120` و `PIP_RETRIES=10` به Dockerfile اضافه شد (کمک کرد ولی کافی نبود).
  - Dockerfile سالم است: در ابتدای همین جلسه build موفق بود.
  - گزینه‌ها: (۱) تلاش مجدد وقتی شبکه پایدار است؛ (۲) build arg اختیاری `PIP_INDEX_URL` برای mirror داخلی (انتخاب mirror با کاربر)؛ (۳) proxy یا VPN برای Docker.
