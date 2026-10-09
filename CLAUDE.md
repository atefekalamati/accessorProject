# CLAUDE.md — Project AK (ATK) Backend

## ۱. معرفی پروژه

بک‌اند API فروشگاه آنلاین اکسسوری Project AK که مستقیم و بدون واسطه به مشتری می‌فروشد: کاتالوگ با تنوع رنگ/سایز/مدل، سبد خرید مهمان و کاربر، ورود با موبایل و OTP، checkout و پرداخت آنلاین.
پنل مدیریت برای محصول، موجودی، قیمت، کد تخفیف، سفارش، مشتری و محتوا، همراه با Audit Log برای عملیات حساس.
وضعیت فعلی: فقط foundation و لایه دیتابیس پایه ساخته شده؛ هیچ منطق فروشگاهی هنوز پیاده نشده است (جزئیات در `docs/project/PROGRESS.md`).

## ۲. معماری

- **Modular Monolith**: یک برنامه FastAPI، ماژول‌ها زیر `app/modules/<name>/`، APIها زیر `/api/v1`.
- الگوی لایه‌ها (از `app/shared/health/` و `app/shared/database/`): `router.py` (HTTP نازک) → `service.py` (منطق) → `repository.py` (دسترسی داده)، به‌علاوه `schemas.py` (Pydantic) و `dependencies.py` (سیم‌کشی `Depends`).
- مدل‌های SQLAlchemy فعلاً متمرکز در `app/db/models/` هستند و در `app/db/models/__init__.py` export می‌شوند.
- ماژول‌های `app/modules/{auth,catalog,inventory,cart,checkout,orders,payments,content,admin}` فعلاً فقط `__init__.py` خالی دارند.
- ماژول‌های هدف (از PRD) که هنوز پوشه ندارند: pricing، discount، shipping/address، customer account، audit، monitoring.

## ۳. ساختار repository

```
app/core/            config (pydantic-settings)، errors، logging JSON، middleware request-id، time (UTC)
app/db/              base (naming convention)، session، seed، models/
app/api/v1/router.py تجمیع routerهای /api/v1
app/modules/         ماژول‌های دامنه (خالی)
app/shared/          health و database readiness (نمونه مرجع لایه‌بندی)
alembic/versions/    migrationها (فعلاً 20260913_0001)
tests/               تست‌ها (تخت، بدون زیرپوشه)
docs/                dbeaver.md + project/ (برنامه‌ریزی)
tasks/               یک فایل برای هر task
sources/             PRD و نقشه راه قدیمی (مرجع، ویرایش نشود)
```

## ۴. Stack فنی (از repo)

Python 3.12 · FastAPI · Pydantic v2 + pydantic-settings · SQLAlchemy 2 async + asyncpg · PostgreSQL 16 · Alembic · PyJWT · passlib/bcrypt · pytest + pytest-asyncio + httpx · ruff · mypy (strict) · hatchling · Docker Compose.
تصمیم‌های باز (درگاه پرداخت، SMS، ذخیره فایل، محیط production و...) در `docs/project/DECISIONS.md`.

## ۵. دستورات توسعه (در 2026-09-29 اجرا و تأیید شدند، به‌جز نصب، `ruff format .` و `docker compose up`)

محیط: Windows، venv در `.venv`. یا venv را فعال کن (`.\.venv\Scripts\Activate.ps1`) یا از `.venv/Scripts/python -m ...` استفاده کن.

```powershell
python -m pip install -e ".[dev]"        # نصب
uvicorn app.main:app --reload            # اجرا (نیاز به .env یا DATABASE_URL و JWT_SECRET)
python -m pytest                         # تست (بدون TEST_DATABASE_URL، تست‌های integration skip می‌شوند)
python -m ruff check .                   # lint
python -m ruff format --check .          # بررسی format   (اعمال: python -m ruff format .)
python -m mypy app tests                 # type-check
alembic upgrade head | alembic current | alembic downgrade -1
python -m app.db.seed                    # seed idempotent نقش‌ها
docker compose up --build                # API + PostgreSQL؛ پورت‌های host از DB_HOST_PORT و API_HOST_PORT در .env
```

دیتابیس تست یک‌بارمصرف: سرویس `postgres-test` با profile `test` و بدون volume. پورت host از `TEST_DB_HOST_PORT` خوانده می‌شود (پیش‌فرض 55432). نام دیتابیس باید با `_test` تمام شود، وگرنه `conftest` کل session را abort می‌کند (exit 3):

```powershell
docker compose --profile test up -d --wait postgres-test
$env:TEST_DATABASE_URL = "postgresql+asyncpg://postgres:test@127.0.0.1:55432/project_ak_test"  # پورت = TEST_DB_HOST_PORT؛ 127.0.0.1 نه localhost (روی Windows ~5x کندتر)
python -m pytest -q
docker compose --profile test stop postgres-test; docker compose --profile test rm -f postgres-test
```

Migration جدید: `alembic revision --autogenerate --rev-id YYYYMMDD_NNNN -m "..."` (قرارداد نام‌گذاری موجود)، سپس خروجی را دستی بازبینی کن.

## ۶. قوانین کدنویسی

- اول از الگوهای موجود repo پیروی کن. کد، شناسه‌ها، کامنت‌ها و commit message انگلیسی باشند.
- `from __future__ import annotations`، type hint کامل، mypy strict باید سبز بماند. طول خط ۱۰۰.
- handler نازک؛ منطق در service. محاسبه قیمت یک تابع خالص (pure) و unit-testable است.
- providerهای بیرونی (درگاه پرداخت، SMS) پشت interface با پیاده‌سازی fake برای تست و development.
- خطاها با `AppError(code=..., message=..., status_code=...)` از `app/core/errors.py`. شکل پاسخ خطا ثابت است: `{"error":{"code","message","details"},"request_id"}`. validation → 400، نقض قانون کسب‌وکار → 422، رزرو منقضی → 409 `RESERVATION_EXPIRED` (ADR-011، ADR-008).
- زمان فقط با `app/core/time.utc_now()`؛ ستون‌ها `DateTime(timezone=True)`.
- مدل جدید: mixinهای `app/db/models/common.py`، export در `app/db/models/__init__.py`، افزودن به `_MODELS` در `alembic/env.py`، و به‌روزکردن `EXPECTED_TABLES` و revision در `tests/test_database.py`.
- تنظیمات جدید فقط از طریق `Settings` در `app/core/config.py` و placeholder در `.env.example`.
- تغییر کوچک و برگشت‌پذیر. refactor بزرگ فقط با توضیح سود/هزینه/ریسک و تأیید کاربر. dependency جدید فقط با ذکر دلیل.

## ۷. قوانین تست

- تست‌ها در `tests/` با نام `test_<area>.py`؛ `asyncio_mode = auto`؛ client از fixture `client` در `tests/conftest.py`.
- تست نیازمند PostgreSQL را با `pytestmark = pytest.mark.integration` علامت بزن و از `TEST_DATABASE_URL` استفاده کن.
- پوشش لازم: unit برای منطق خالص (قیمت، تخفیف، موجودی آزاد)؛ API برای هر endpoint شامل مسیرهای 400/401/403/404/409/422؛ تست همزمانی موجودی؛ تست idempotency برای ایجاد سفارش و callback پرداخت؛ یک تست end-to-end خرید.
- **Definition of Done**: همه معیارهای پذیرش task تیک خورده، و `pytest` (با دیتابیس تست)، `ruff check`، `ruff format --check` و `mypy app tests` همه سبز باشند. فایل task و PROGRESS.md هم به‌روز شده باشند. نوشتن کد به‌تنهایی یعنی COMPLETE نیست.

## ۸. محدودیت‌های حیاتی

- قیمت و مبلغ نهایی فقط در بک‌اند محاسبه می‌شود. price/amount/stock/role یا هر فیلد سیستمی ارسالی از کلاینت نادیده گرفته شود.
- پول = عدد صحیح **تومان** (نه float). گردکردن فقط یک‌بار و در pricing service. تبدیل به ریال فقط داخل adapter درگاه (ADR-001).
- `OrderItem` snapshot عنوان و قیمت واحد لحظه خرید را نگه می‌دارد.
- موجودی per ProductVariant؛ `free = total − active reservations`؛ افزودن به سبد رزرو نمی‌کند؛ رزرو ۱۵ دقیقه هنگام `POST /orders`، پایان با commit یا release (ADR-007). موجودی فقط در InventoryItem و در v1 یک انبار پیش‌فرض (ADR-005).
- عملیات موجودی/سفارش/پرداخت تراکنشی با row lock (`SELECT ... FOR UPDATE`)؛ oversell ممنوع.
- Callback پرداخت: verify با درگاه، مبلغ == `grandTotal`، idempotent، مصرف‌نکردن رزرو منقضی.
- OTP و refresh token هش‌شده؛ OTP یک‌بارمصرف، دارای انقضا و rate-limit (429). refresh فقط در cookie `HttpOnly; Secure; SameSite=Strict` و access در body (ADR-012). ثبت نهایی سفارش فقط با موبایل تأییدشده.
- RBAC: فقط Super Admin نقش تغییر می‌دهد. بررسی مالکیت برای سفارش، سبد و آدرس.
- تغییرات حساس (قیمت، موجودی، وضعیت سفارش، نقش، کد تخفیف) در `audit_logs` (حذف آن با trigger ممنوع است).
- Product و Variant ارجاع‌شده soft delete می‌شوند. SD rule: read عمومی (list/detail) رکورد soft-deleted را برنمی‌گرداند (detail → 404 `NOT_FOUND`) و write ارجاع‌دهنده (سبد، checkout validate، ایجاد سفارش) آن را رد می‌کند (PLAN.md). Order سه وضعیت مستقل دارد: order، payment، shipment.
- secretها فقط در `.env` (gitignored). `.env.example` فقط placeholder. `TEST_DATABASE_URL` هرگز به دیتابیس shared/production اشاره نکند (تست‌ها downgrade می‌کنند).
- پورت محلی اشغال بود: اولین پورت آزاد بعدی را انتخاب کن، در `.env` بگذار (`DB_HOST_PORT`/`API_HOST_PORT`) و فقط گزارش بده؛ هرگز پروسه یا containerی را kill نکن.
- دستورات مخرب (`docker compose down -v`، `alembic downgrade` روی دیتابیس واقعی، `DROP`) فقط با تأیید صریح.

## ۹. Git و مدیریت تغییر

- شاخه اصلی `master` است. یک شاخه برای هر فاز، مثل `feat/phase-2-core-domain`. در پایان فاز، شاخه از طریق PR در `master` merge می‌شود. استثنا: فاز ۱ روی `feat/m1.1-repo-foundation` است (M1.1 و M1.2 مشترک).
- Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`, `test:`, `refactor:`).
- بدون درخواست صریح: هرگز push (به‌جز push بعد از `/done`، بخش ۱۱)، force-push، `reset --hard`، rebase روی `master`، یا ویرایش migration commit‌شده.
- تغییر schema فقط با migration جدید.

## ۱۰. استفاده از PRD

- فایل: `sources/Project-AK-PRD.md` (فارسی، ~۸۳۵۰ خط). هرگز کامل نخوان و import نکن.
- فهرست بخش‌ها: `grep -n "^## \|^### " sources/Project-AK-PRD.md`، سپس فقط همان بخش را با `sed -n 'A,Bp'` بخوان.
- **مرجع (authoritative)**، هشت بخش: «معماری سیستم» و هفت بخش علامت‌دار ✓: «هویت و دسترسی»، «قیمت و مالیات»، «موجودی و رزرو»، «صفحه اصلی»، «دسته‌بندی محصولات»، «جزئیات محصول»، «محصولات» (پنل مدیریت).
- **قالبی (templated)**، ۳۱ بخش دیگر (از «جست‌وجو» به بعد): متن یکسان با تغییر نام صفحه، entity و path (تأییدشده: ۱۵ خط تفاوت از ۲۰۵). endpointهای CRUD عمومی آن‌ها (مثل `DELETE /payments/{id}`) را عیناً پیاده نکن. اول task نیازمندی `<PREFIX>-00` آن milestone انجام و تأیید شود.
- تعارض: بخش مرجع برنده است. اگر هنوز مبهم بود → ثبت در `DECISIONS.md` و پرسیدن از کاربر.
- `sources/backend-roadmap-fastapi.md` نقشه راه قدیمی است (مرحله ۰ و ۱ آن انجام شده). فقط مرجع جزئیات؛ نقشه راه معتبر `docs/project/ROADMAP.md` است.

## ۱۱. برنامه‌ریزی و گردش کار

فایل‌های برنامه‌ریزی، مراحل هر task، قواعد تغییر برنامه و نگاشت درخواست‌های رایج («کجاییم؟»، «قدم بعدی؟» و…) در [docs/project/WORKFLOW.md](docs/project/WORKFLOW.md) هستند. بدون validation هرگز COMPLETE نزن و به درخواست‌های وضعیت همیشه از فایل‌ها جواب بده.

- هر task قبل از اجرا plan تأییدشده توسط کاربر لازم دارد.
- هر فایل task یک خط `Level: LOW|MEDIUM|HIGH` دارد.
- HIGH شامل این موارد است: موجودی/رزرو، پرداخت، OTP/token/auth، ویرایش PRD، تغییر رفتار API، و هر task که مبلغ پولی، موجودی، مصرف کد تخفیف یا وضعیت سفارش/پرداخت را محاسبه یا ذخیره کند. plan این taskها باید ریسک‌ها، مراحل rollback و تست‌های اضافه را هم فهرست کند.
- بعد از هر `/done`، شاخه فعلی push شود (`git push`، بدون force).

### Batch mode (`/batch`، جزئیات در `.claude/commands/batch.md`)

- پیشنهاد: ۳ تا ۵ task مرتبط و بعدی از milestone جاری، جمعاً حداکثر ~8h (اگر هیچ task HIGH نباشد حداکثر ~12h و کاربر مستقیم با «ok» تأیید می‌کند)، با **یک** plan مشترک. برای هر task با Level HIGH، ریسک‌ها، rollback و تست‌های اضافه جداگانه نوشته شود. تا تأیید صبر کن.
- بعد از تأیید، برای هر task به ترتیب:
  1. پیاده‌سازی
  2. pytest، ruff و mypy
  3. self-review diff در برابر معیارهای پذیرش و قوانین CLAUDE.md
  4. به‌روزرسانی فایل task و PROGRESS.md
  5. commit و push

  سپس بدون صبر برو سراغ task بعدی.
- **توقف فوری** وقتی یکی از این‌ها پیش بیاید: تستی با علت نامشخص fail شود؛ تصمیم باز یا ابهام در PRD پیدا شود؛ کاری خارج از plan تأییدشده لازم شود؛ تغییر schema یا migration برنامه‌ریزی‌نشده لازم شود.
- **هرگز batch نشوند:** taskهای `PAY-*` و taskهای رزرو، commit یا release موجودی. هر کدام در یک جلسه جدا انجام می‌شود.
- پایان batch: یک گزارش واحد شامل یک خط برای هر task (ID، وضعیت، commit، تست‌ها)، جمع کل و پیشنهاد batch بعدی. از کاربر بخواه CI را بررسی کند.

## ارتباط با کاربر

فارسی صحبت کن؛ اصطلاح فنی انگلیسی بماند. واقعیت (در repo)، استنتاج و پیشنهاد را جدا کن.

## پروتکل جلسه و صرفه‌جویی توکن

1. CLAUDE.md خودکار بارگذاری می‌شود؛ دوباره نخوان.
2. شروع جلسه: فقط بخش «Current / Next» در `docs/project/PROGRESS.md` و فایل task فعلی. ROADMAP و PLAN فقط هنگام تغییر فاز یا درخواست کاربر.
3. PRD: فقط grep و خواندن همان بخش؛ هرگز کل فایل.
4. هر جلسه یک task (استثنا: `/batch`). بعد از اتمام و commit بگو «آماده برای /clear».
5. تست و lint با خروجی کم (`pytest -q`)؛ فقط خطاها را نشان بده.
6. فایل کامل را در پاسخ تکرار نکن؛ فقط خلاصه diff.
7. اصطلاح جدید فقط بار اول و در یک خط توضیح داده شود.
8. سؤال‌ها را جمع کن و یک‌جا در آخر بپرس. سؤال کم‌اثر را نپرس: با پیشنهاد خودت تصمیم بگیر و در `DECISIONS.md` ثبت کن. فقط سؤال‌های امنیت، پول، از دست رفتن داده یا محدوده PRD پرسیده شوند.
9. هر گزارش با این هدر (متن ساده، بدون emoji) شروع شود و کل گزارش حداکثر ۱۰ خط باشد:
   ```
   موقعیت: فاز › milestone › task — وضعیت
   پیشرفت: انجام‌شده/کل task | ٪ وزنی
   مانع‌ها: ...
   قدم بعد: ...
   ```
