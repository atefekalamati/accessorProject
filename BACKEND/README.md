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
$env:TEST_DATABASE_URL = "postgresql+asyncpg://postgres:test@127.0.0.1:55432/project_ak_test"  # پورت = TEST_DB_HOST_PORT؛ 127.0.0.1 نه localhost (روی Windows ~5x کندتر)
pytest
docker compose --profile test stop postgres-test
docker compose --profile test rm -f postgres-test
```

این تست‌ها چرخه `upgrade -> downgrade -> upgrade` را اجرا می‌کنند. اگر نام دیتابیس در `TEST_DATABASE_URL` با `_test` تمام نشود، کل session تست قبل از اجرای هر تستی متوقف می‌شود (exit code 3). هرگز `TEST_DATABASE_URL` را به دیتابیس shared یا production متصل نکنید.

## Secret scanning

در CI، job `secret-scan` با gitleaks نسخه pin‌شده `8.30.1` (همراه با بررسی sha256) کل تاریخچه git را اسکن می‌کند. هر finding باعث fail شدن CI می‌شود. قوانین و allowlist در [`.gitleaks.toml`](.gitleaks.toml) هستند. هر مورد allowlist باید به یک fixture ساختگی مشخص محدود باشد و دلیل مکتوب داشته باشد.

اجرای محلی (اختیاری، با Docker و همان نسخه):

```powershell
docker run --rm -v "${PWD}:/repo" -w /repo ghcr.io/gitleaks/gitleaks:v8.30.1 git --config .gitleaks.toml --redact --exit-code 1 -v .
```

## مستندات API

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`
- Readiness: `http://localhost:8000/ready` و `http://localhost:8000/api/v1/ready`
- وضعیت دیتابیس development/test: `http://localhost:8000/api/v1/dev/database-status`

## پرداخت و go-live checklist

درگاه با `PAYMENT_PROVIDER` انتخاب می‌شود: `fake` (development و staging) یا `zarinpal` (Zarinpal v4، ADR-064). تنظیمات Zarinpal: `ZARINPAL_MERCHANT_ID` (secret؛ فقط در `.env`) و `ZARINPAL_SANDBOX` (پیش‌فرض `true`). `PAYMENT_CALLBACK_URL` به صفحه نتیجه frontend اشاره می‌کند (`docs/api/FRONTEND.md` §۷). در production هر درگاهی، از جمله Zarinpal، تا go-live رد می‌شود (fail-closed).

قبل از فعال‌کردن پرداخت واقعی در production:

- [ ] D13 (محیط production) تصمیم گرفته شده و OPS-04 (proxy مورد اعتماد، IP واقعی برای rate limit callback) COMPLETE است. D9 و D10 (SMS و storage واقعی) هم جداگانه لازم‌اند.
- [ ] E2E دستی sandbox یک‌بار اجرا و نتیجه در Log فایل `tasks/phase-05/PAY-07-zarinpal-gateway.md` ثبت شده است: پرداخت موفق، لغو، reload صفحه نتیجه (101)، و عمر authority (فرض ۱۵ دقیقه).
- [ ] merchant id واقعی از پنل Zarinpal فقط در secret store یا `.env` سرور است، نه در repo، log یا image.
- [ ] دامنه `PAYMENT_CALLBACK_URL` همان دامنه ثبت‌شده در پنل Zarinpal است (وگرنه کد -14) و `https` است.
- [ ] `ZARINPAL_SANDBOX=false` و `PAYMENT_PROVIDER=zarinpal`.
- [ ] تنظیم auto-verify در پنل Zarinpal بررسی و ثبت شده است. بک‌اند `metadata.auto_verify` نمی‌فرستد، پس تنظیم پنل اعمال می‌شود. با auto-verify روشن، verify ما 101 می‌گیرد، که همچنان PAID است، ولی اگر callback و reconciliation هر دو گم شوند پول بدون سفارش settle می‌ماند و فقط با `unVerified` یا پنل پیدا می‌شود. پیشنهاد: خاموش.
- [ ] `PAYMENT_MAX_AMOUNT` (پیش‌فرض ۱۰۰٬۰۰۰٬۰۰۰ تومان) با سقف واقعی terminal در پنل Zarinpal یکی است.
- [ ] حداقل مبلغ Zarinpal (در docs نیامده؛ در E2E sandbox با یک سفارش کم‌مبلغ بررسی شود) ثبت شده است. اگر سفارشی زیر آن ممکن است، یک حداقل در init لازم است، وگرنه request جواب 503 می‌گیرد.
- [ ] guard production در `build_payment_gateway` (`app/modules/payments/gateways/__init__.py`) با یک task جدا و بازبین opus برداشته شده است. آن task باید `ZARINPAL_SANDBOX=true` و callback غیر https را در production رد کند، و تست قرارداد production (`tests/test_provider_contracts.py`) را هم به‌روز کند.
- [ ] هنگام تعویض provider هیچ payment در وضعیت `pending` باز نیست (reconciliation آن‌ها را با درگاه جدید verify می‌کند و فقط `abandoned` می‌شوند).
- [ ] alert روی logهای `payment.zarinpal_merchant_refused`، `payment.zarinpal_amount_rejected` و `payment.zarinpal_unexpected_answer` (OPS-02) و روند بازپرداخت دستی `refund_required` (ADM-08) آماده است.
- [ ] بررسی حقوقی بازپرداخت هزینه ارسال در مرجوعی (D44) انجام شده است.

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
