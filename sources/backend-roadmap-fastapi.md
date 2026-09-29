# نقشه اجرای بک‌اند Project AK

## هدف و قرارداد اجرا

بک‌اند فروشگاه با `Python 3.12`، `FastAPI`، `PostgreSQL 16`، `SQLAlchemy 2`، `Alembic`، `Pydantic v2`، `pytest` و `Docker Compose` ساخته می‌شود. معماری نسخه اول **Modular Monolith** است؛ APIها زیر `/api/v1`، مستندات Swagger در `/docs` و قرارداد OpenAPI در `/openapi.json` قرار می‌گیرند.

هر مرحله تنها پس از چهار تأیید جلو می‌رود: اجرای تست‌ها، بررسی Swagger، اجرای migration و تطبیق پاسخ API با نیاز فرانت‌اند. درصدها تجمعی‌اند و بر اساس خروجی قابل‌قبول ثبت می‌شوند.

## تصمیم‌های پایه نسخه اول

| موضوع | تصمیم |
|---|---|
| مدل فروش | تک‌فروشگاهی؛ محصولات متعلق به برند |
| احراز هویت | شماره موبایل و OTP؛ خرید مهمان مجاز است ولی ثبت سفارش با شماره تأییدشده انجام می‌شود |
| پول | تومان، نگهداری مبلغ به عدد صحیح ریال در دیتابیس؛ نمایش تومان در API با فیلد صریح |
| انبار | یک انبار فعال در V1؛ طراحی داده آماده چندانباره شدن |
| نقش‌ها | `customer`، `admin`، `content_manager`، `warehouse_manager`، `support` |
| رزرو موجودی | هنگام آغاز پرداخت، 15 دقیقه؛ آزادسازی خودکار پس از انقضا یا شکست پرداخت |
| حذف داده | Soft delete برای محصول و داده‌های قابل‌ارجاع؛ سفارش و پرداخت immutable هستند |

## نقشه راه و درصد پیشرفت

| مرحله | خروجی قابل تحویل | درصد تجمعی |
|---|---|---:|
| 0. قرارداد فنی و ریپازیتوری | ساختار پروژه، Docker، تنظیمات، CI پایه | 8% |
| 1. پایگاه داده و Migration | PostgreSQL، Alembic، مدل‌های پایه، DBeaver | 18% |
| 2. هویت و مجوزها | OTP، JWT، RBAC، session | 30% |
| 3. کاتالوگ و صفحه اصلی | دسته‌بندی، محصول، واریانت، محتوای home | 45% |
| 4. جست‌وجو و فیلتر | listing، sort، pagination و query contract | 53% |
| 5. قیمت، تخفیف و موجودی | price snapshot، coupon، reservation | 65% |
| 6. سبد و checkout | سبد مهمان/کاربر، آدرس، ارسال، ثبت سفارش | 76% |
| 7. پرداخت و پیگیری سفارش | gateway adapter، callback idempotent، سفارش‌ها | 86% |
| 8. پنل مدیریت و پشتیبانی | CRUD امن، مرجوعی، audit log | 94% |
| 9. کیفیت، امنیت و استقرار | تست end-to-end، rate limit، monitoring، release | 100% |

## چرخه کار هر مرحله

1. پرامپت همان مرحله را اجرا کن.
2. این خروجی‌ها را بفرست: درخت فایل‌های جدید، خروجی `pytest`، خروجی `alembic current`، لینک یا JSON بخش مرتبط Swagger و خطاهای احتمالی.
3. من خروجی را با PRD، قرارداد API و دیتابیس بررسی می‌کنم؛ درصد واقعی پیشرفت را ثبت و پرامپت مرحله بعد را می‌دهم.
4. هیچ endpointی بدون schema پاسخ، migration و تست حداقلی نهایی نمی‌شود.

---

## مرحله 0: قرارداد فنی و اسکلت پروژه | 0% تا 8%

### پرامپت مرحله 0

```text
برای پروژه فروشگاه Project AK یک بک‌اند production-ready با Python 3.12 و FastAPI بساز. هنوز منطق کسب‌وکار کامل را پیاده نکن؛ فقط foundation تمیز و قابل توسعه بساز.

فناوری‌های اجباری:
- FastAPI، Uvicorn، Pydantic v2، pydantic-settings
- SQLAlchemy 2 async، asyncpg، Alembic
- PostgreSQL 16 با Docker Compose
- pytest، pytest-asyncio، httpx، ruff، mypy (پیکربندی پایه)
- JWT libraries و passlib/bcrypt را فقط به dependencies اضافه کن؛ auth کامل در مرحله بعد است.

ساختار مدولار مورد انتظار:
app/
  api/v1/
  core/
  db/
  modules/{auth,catalog,inventory,cart,checkout,orders,payments,content,admin}/
  shared/
tests/
alembic/

الزامات:
1) فایل .env.example با DATABASE_URL، JWT_SECRET، ENVIRONMENT، CORS_ORIGINS و تنظیمات OTP mock.
2) docker-compose.yml با سرویس api و postgres؛ volume پایدار و healthcheck PostgreSQL.
3) endpointهای GET /health و GET /api/v1/health با پاسخ شامل status، version و environment.
4) CORS فقط از env خوانده شود و wildcard در production ممنوع باشد.
5) request-id middleware، handler یکپارچه خطا، logging ساختاریافته و زمان UTC.
6) Swagger در /docs، ReDoc در /redoc و OpenAPI در /openapi.json فعال باشد.
7) README شامل دستور دقیق اجرا، تست، lint و migration باشد.
8) تست برای health endpoint و تنظیمات محیط بساز.

قواعد کیفیت:
- type hints کامل، dependency injection FastAPI و لایه‌بندی router/service/repository.
- secretها در git نباشند.
- پاسخ خطا شکل ثابت داشته باشد: {"error":{"code":"...","message":"...","details":[]},"request_id":"..."}.

در پایان فقط این گزارش را بده: فایل‌های ساخته‌شده، دستورات اجرا، نتیجه تست/lint، و هر تصمیمی که نیاز به تأیید دارد.
```

### بررسی خروجی مرحله 0

- `docker compose up --build` باید API و PostgreSQL سالم بالا بیاورد.
- `GET /health` باید `200` و `request_id` بازگرداند.
- Swagger باید بدون خطا schema را نشان دهد.
- `pytest` و `ruff check .` باید موفق باشند.

### پرامپت مرحله بعد، پس از تأیید

پرامپت مرحله 1 را اجرا کن.

---

## مرحله 1: PostgreSQL، Alembic و نمایش DBeaver | 8% تا 18%

### پرامپت مرحله 1

```text
روی foundation موجود Project AK، لایه دیتابیس PostgreSQL و Alembic را کامل کن. SQLAlchemy async استفاده کن، اما migrationهای Alembic باید قابل اجرا و قطعی باشند.

مدل‌های پایه را ایجاد کن:
- users: id UUID، phone unique، status، full_name nullable، created_at، updated_at، deleted_at
- roles، permissions، user_roles، role_permissions
- addresses: user_id، recipient_name، phone، province، city، postal_code، address_line، plaque، unit، is_default
- audit_logs: actor_user_id nullable، action، entity_type، entity_id، metadata JSONB، ip، created_at
- app_settings: key unique، value JSONB، updated_at

الزامات دیتابیس:
1) UUID و timezone-aware UTC، نام‌گذاری ثابت برای همه constraint/indexها.
2) unique و foreign keyهای لازم، index روی phone، user_id، created_at و فیلدهای جست‌وجوشونده.
3) soft delete فقط برای users؛ داده‌های audit هرگز حذف نشوند.
4) migration ابتدایی Alembic بساز و upgrade/downgrade را تست کن.
5) seed idempotent برای نقش‌ها: customer, admin, content_manager, warehouse_manager, support.
6) endpoint فقط برای توسعه: GET /api/v1/dev/database-status که در production غیرفعال باشد.
7) docker-compose برای اتصال DBeaver آماده باشد: Host=localhost, Port=5432, Database=project_ak, User=project_ak, Password از .env.
8) یک فایل docs/dbeaver.md با مراحل اتصال، ERD entities و queryهای بررسی بنویس.
9) تست migration، seed و constraintهای اصلی اضافه کن.

خروجی نهایی: نام migration، ERD متنی، دستور اتصال DBeaver، نتیجه pytest و alembic current.
```

### بررسی خروجی مرحله 1

- اجرای `alembic upgrade head` روی دیتابیس خالی موفق باشد.
- اتصال DBeaver با تنظیمات مستندشده برقرار شود و جدول‌ها قابل مشاهده باشند.
- نقش‌ها با اجرای مجدد seed تکراری نشوند.
- downgrade و upgrade مجدد بدون خطا انجام شود.

---

## مرحله 2: هویت، OTP و RBAC | 18% تا 30%

### پرامپت مرحله 2

```text
ماژول auth را برای Project AK پیاده‌سازی کن. ورود با شماره موبایل ایران و OTP است. در development ارسال OTP mock/logged باشد و در production فقط adapter قابل تعویض provider استفاده شود.

Endpointها:
- POST /api/v1/auth/otp/request
- POST /api/v1/auth/otp/verify
- POST /api/v1/auth/refresh
- POST /api/v1/auth/logout
- GET /api/v1/auth/me

قواعد:
1) شماره موبایل E.164 ایران (+989...) یا 09... را normalize کن.
2) OTP شش‌رقمی، hash شده، 2 دقیقه معتبر، حداکثر 5 تلاش و rate-limit بر مبنای phone/IP.
3) verify موفق کاربر را ایجاد/فعال کند و access/refresh token برگرداند.
4) refresh token قابل ابطال، rotation و family tracking داشته باشد.
5) RBAC dependency بساز؛ admin به همه، هر نقش فقط permissionهای خودش.
6) endpointهای admin بعداً نباید با role سمت کلاینت قابل جعل باشند.
7) schemaهای پاسخ و خطا را در Swagger دقیق کن و تست abuse cases بنویس.

خروجی نهایی: جدول endpoint و status codeها، نتیجه تست‌ها و نمونه پاسخ Swagger.
```

### بررسی اتصال فرانت در این مرحله

- فرانت فقط access token کوتاه‌عمر را نگه می‌دارد؛ refresh token در cookie امن HttpOnly یا الگوی مورد تأیید نهایی قرار می‌گیرد.
- در `401`، فرانت یک refresh کنترل‌شده انجام می‌دهد و loop نمی‌سازد.
- `GET /auth/me` منبع حقیقت نقش و اطلاعات کاربر است.

---

## مرحله 3: کاتالوگ و محتوای صفحه اصلی | 30% تا 45%

### پرامپت مرحله 3

```text
ماژول catalog و content Project AK را پیاده کن. محصول دارای category، collection، media و variant است و قیمت/موجودی در variant نگهداری می‌شود.

Entityهای لازم: categories، collections، products، product_variants، product_media، attributes، attribute_values، variant_attribute_values، homepage_sections، homepage_items.

API عمومی:
- GET /api/v1/home
- GET /api/v1/categories
- GET /api/v1/categories/{slug}
- GET /api/v1/products/{slug}

API مدیریتی زیر /api/v1/admin برای CRUD و publish/unpublish.

قواعد: slug unique، محصول draft/published/archived، محصول منتشرشده حداقل یک variant فعال و media اصلی داشته باشد، archived در API عمومی دیده نشود، ترتیب media و homepage قابل کنترل باشد. پاسخ محصول باید contract ثابت برای فرانت داشته باشد و به N+1 query دچار نشود.

تست authorization، publish validation، slug conflict و پاسخ public اضافه کن. OpenAPI و seed نمونه ایجاد کن.
```

---

## مرحله 4: لیست، جست‌وجو، فیلتر و صفحه‌بندی | 45% تا 53%

### پرامپت مرحله 4

```text
برای catalog API لیست محصول بساز:
GET /api/v1/products با فیلتر category، collection، price_min، price_max، attributes، in_stock، q، sort و cursor pagination.

قواعد: فقط محصولات published و variantهای فعال، sortهای newest/price_asc/price_desc/bestselling، validate queryها، حداکثر page size=48 و cursor opaque. پاسخ شامل items، next_cursor، applied_filters، available_filters و total_estimate باشد. indexهای PostgreSQL لازم برای query plan اضافه کن و با EXPLAIN ANALYZE بررسی کن.

تست ترکیب فیلترها، cursor خراب، sort نامعتبر و فیلتر موجودی را اضافه کن. نمونه requestها را در Swagger قرار بده.
```

### قرارداد فرانت

- URL صفحه category باید queryهای API را مستقیم و قابل share نگه دارد.
- فرانت هر بار فیلترها را از `available_filters` نمایش می‌دهد، نه از یک لیست hard-coded.

---

## مرحله 5: قیمت، تخفیف، موجودی و رزرو | 53% تا 65%

### پرامپت مرحله 5

```text
ماژول pricing، inventory و promotions را برای Project AK بساز.

Entityها: warehouses، inventory_levels، inventory_movements، inventory_reservations، price_history، coupons، coupon_redemptions.

قواعد کسب‌وکار:
- مبلغ دیتابیس integer ریال؛ API price_rials و display_tomans برگرداند.
- قیمت نهایی فقط سرور محاسبه شود؛ در checkout snapshot ذخیره شود.
- available = on_hand - reserved؛ موجودی هر variant مستقل است.
- رزرو پرداخت 15 دقیقه و فقط با transaction/row lock ایجاد شود؛ job آزادسازی idempotent داشته باشد.
- کد تخفیف زمان، حداقل خرید، سقف تخفیف، سقف مصرف کل/هر کاربر و category/product exclusion دارد.
- API داخلی quote باید قیمت، مالیات، ارسال و discount breakdown را برگرداند.

Endpointهای public/cart و admin inventory/coupons را کامل کن، migration و concurrent reservation tests اضافه کن.
```

---

## مرحله 6: سبد، آدرس، ارسال و ایجاد سفارش | 65% تا 76%

### پرامپت مرحله 6

```text
ماژول‌های cart و checkout را بساز.

Endpointها: GET/POST/PATCH/DELETE /api/v1/cart/items، POST /api/v1/cart/merge، GET/POST/PATCH/DELETE /api/v1/addresses، POST /api/v1/checkout/quote، POST /api/v1/checkout/orders.

قواعد: cart مهمان با cart token امن، پس از login merge قطعی، quantity بین 1 و موجودی قابل خرید، سفارش تنها از quote معتبر و بدون تغییر price/inventory ساخته شود، آدرس snapshot سفارش است، سفارش idempotency key اجباری دارد، محاسبه ارسال از adapter مستقل انجام می‌شود.

Entityها: carts، cart_items، shipping_methods، orders، order_items، order_addresses، order_status_history. تست merge، price-changed، insufficient-stock و duplicate create order را اضافه کن.
```

### کنترل اتصال فرانت

- فرانت مبلغ را فقط برای نمایش نشان می‌دهد و قبل از پرداخت `checkout/quote` تازه می‌گیرد.
- درخواست ایجاد سفارش header `Idempotency-Key` دارد.
- conflict قیمت یا موجودی به یک state قابل فهم در UI تبدیل می‌شود.

---

## مرحله 7: پرداخت و چرخه سفارش | 76% تا 86%

### پرامپت مرحله 7

```text
ماژول payment و order tracking را بساز. یک PaymentGateway interface و یک MockGateway واقعی برای development بنویس؛ درگاه ایرانی آینده فقط adapter جدید باشد.

Endpointها: POST /api/v1/payments/initiate، POST /api/v1/payments/callback/{provider}، GET /api/v1/orders، GET /api/v1/orders/{public_id}.

قواعد: callback با verify سمت سرور، idempotent، ثبت raw event redact شده، پرداخت و سفارش status مستقل، success فقط پس از verify معتبر، شکست/انقضا رزرو را آزاد کند، transitionهای order state machine معتبر باشند. admin بتواند shipment/tracking code ثبت کند. تست callback تکراری، امضای نامعتبر، timeout و status transition را اضافه کن.
```

---

## مرحله 8: پنل مدیریت، پشتیبانی و Audit | 86% تا 94%

### پرامپت مرحله 8

```text
APIهای admin و support را تکمیل کن: dashboard metrics، product/media/category/collection CRUD، inventory adjustment، coupon، homepage content، order operations، customer lookup، return request و notes.

همه endpointهای مدیریتی permission-based باشند. هر mutation حساس در audit_logs با actor، before/after امن، request_id و زمان ثبت شود. Bulk actionها سقف و validation داشته باشند. لیست‌ها cursor pagination و search داشته باشند. هیچ secret، token یا داده پرداختی کامل در API یا log برنگردد.

تست role matrix، audit log و validation را اضافه کن.
```

---

## مرحله 9: کیفیت، امنیت، استقرار و تحویل | 94% تا 100%

### پرامپت مرحله 9

```text
بک‌اند Project AK را برای انتشار آماده کن. CI شامل test، lint، type-check، migration check و dependency scan باشد. rate limit عمومی، security headers، CORS production، request size limit، health/readiness endpoint، structured logging، error tracking adapter و metrics پایه اضافه کن.

OpenAPI را export و version کن. مجموعه تست end-to-end برای auth تا پرداخت mock بساز. seed demo جدا از production داشته باش. Docker image کوچک و non-root باشد. runbook شامل backup/restore PostgreSQL، اجرای migration، rollback، rotate secrets و اتصال DBeaver را بنویس.

خروجی نهایی: گزارش پوشش تست، OpenAPI file، ERD، deployment checklist و فهرست APIهای آماده اتصال به فرانت.
```

## قالب ارسال خروجی برای تحلیل

```text
مرحله: <شماره>
دستورهای اجراشده:
نتیجه pytest / ruff / mypy:
نتیجه migration:
Swagger یا OpenAPI تغییر یافته:
نمونه پاسخ API:
تصمیم یا خطای باز:
```

## معیار اتمام 100 درصد

- تمام APIهای PRD در OpenAPI نسخه‌بندی‌شده ثبت و تست شده‌اند.
- تمام mutationها authorization، validation و audit مناسب دارند.
- قیمت، تخفیف، موجودی، رزرو، سفارش و پرداخت فقط روی سرور معتبر می‌شوند.
- migration از دیتابیس خالی و ارتقای نسخه قبلی تست شده است.
- Swagger برای فرانت قابل استفاده و محیط DBeaver مستند است.
- مسیر end-to-end از OTP تا سفارش پرداخت‌شده با mock gateway سبز است.
