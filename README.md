# Project AK Backend

Foundation بک‌اند فروشگاه Project AK با Python 3.12، FastAPI، SQLAlchemy async و PostgreSQL 16. این مرحله فقط زیرساخت را فراهم می‌کند و منطق احراز هویت و فروشگاه در آن پیاده‌سازی نشده است.

## پیش‌نیازها

- Docker و Docker Compose، یا Python 3.12 و PostgreSQL 16
- یک فایل `.env` محلی که از `.env.example` ساخته شده و مقادیر placeholder آن تغییر کرده‌اند

## اجرا با Docker Compose

```powershell
Copy-Item .env.example .env
# JWT_SECRET و POSTGRES_PASSWORD را در .env تغییر دهید.
docker compose up --build
```

سرویس API روی `http://localhost:8000` و PostgreSQL روی پورت `5432` در دسترس‌اند. دیتای PostgreSQL در volume نام‌دار `postgres_data` پایدار می‌ماند. اگر این پورت‌ها روی سیستم شما اشغال‌اند، `API_HOST_PORT` و `DB_HOST_PORT` را در `.env` تغییر دهید (مثلاً 8001 و 5433) و در آدرس‌های زیر همان پورت‌ها را به کار ببرید.

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/api/v1/health
```

## اجرای محلی

برای اجرای API یا Alembic روی host، در `DATABASE_URL` مقدار host را از `postgres` به `localhost` و پورت را به مقدار `DB_HOST_PORT` تغییر دهید.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

## کیفیت و تست

```powershell
pytest
ruff check .
ruff format --check .
mypy app tests
```

## Migration

```powershell
alembic revision --autogenerate -m "describe change"
alembic upgrade head
alembic current
alembic downgrade -1
python -m app.db.seed
```

Migration اولیه جدول‌های پایه، constraintها و seed نقش‌های سیستمی را می‌سازد. راهنمای کامل اتصال و queryهای بررسی در [`docs/dbeaver.md`](docs/dbeaver.md) قرار دارد.

برای اجرای تست‌های integration، سرویس یک‌بارمصرف `postgres-test` (profile `test`، بدون volume) را بالا بیاورید. پورت host از `TEST_DB_HOST_PORT` در `.env` خوانده می‌شود (پیش‌فرض `55432`). `docker compose up` معمولی این سرویس را بالا نمی‌آورد.

```powershell
docker compose --profile test up -d --wait postgres-test
$env:TEST_DATABASE_URL = "postgresql+asyncpg://postgres:test@localhost:55432/project_ak_test"  # پورت = TEST_DB_HOST_PORT
pytest
docker compose --profile test stop postgres-test
docker compose --profile test rm -f postgres-test
```

این تست‌ها چرخه `upgrade -> downgrade -> upgrade` را اجرا می‌کنند. اگر نام دیتابیس در `TEST_DATABASE_URL` با `_test` تمام نشود، کل session تست قبل از اجرای هر تستی متوقف می‌شود (exit code 3). هرگز `TEST_DATABASE_URL` را به دیتابیس shared یا production متصل نکنید.

## مستندات API

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`
- Readiness: `http://localhost:8000/ready` و `http://localhost:8000/api/v1/ready`
- وضعیت دیتابیس development/test: `http://localhost:8000/api/v1/dev/database-status`

## تنظیمات و امنیت

تمام تنظیمات runtime از environment یا `.env` خوانده می‌شوند. `JWT_SECRET` حداقل ۳۲ کاراکتر است، wildcard در CORS محیط production رد می‌شود و OTP mock نیز در production مجاز نیست. فایل `.env` در `.gitignore` قرار دارد؛ `.env.example` فقط placeholderهای غیرمحرمانه دارد.

هر پاسخ `health` شناسه درخواست را هم در body و هم در header به نام `X-Request-ID` برمی‌گرداند. خطاهای HTTP و validation قرارداد ثابت زیر را دارند:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Error description",
    "details": []
  },
  "request_id": "uuid"
}
```
