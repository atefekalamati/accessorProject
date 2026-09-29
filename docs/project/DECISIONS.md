# DECISIONS — Project AK

وضعیت‌ها: `open` · `deferred` (عمداً به فاز مشخصی موکول شده) · `resolved` (ADR پایین صفحه).
هر تصمیم یک task تصمیم (`DEC-NN`، هم‌شماره با `DNN`) دارد. taskهای ستون «مسدود می‌کند» تا حل آن تصمیم `BLOCKED` می‌مانند.

## فهرست

| ID | موضوع | Task | مسدود می‌کند | وضعیت |
|---|---|---|---|---|
| D1 | Stack فنی | DEC-01 | — | resolved (ADR-003) |
| D2 | نقش‌ها | DEC-02 | — | resolved (ADR-004) |
| D3 | مدل variant و موجودی | DEC-03 | — | resolved (ADR-005) |
| D4 | تعداد انبار | DEC-04 | — | resolved (ADR-005) |
| D5 | endpointهای validate | DEC-05 | — | resolved (ADR-006) |
| D6 | لحظه رزرو | DEC-06 | — | resolved (ADR-007) |
| D7 | HTTP 410 | DEC-07 | — | resolved (ADR-008) |
| D8 | درگاه پرداخت | DEC-08 | PAY-07 | resolved: interface + fake (ADR-009)؛ انتخاب درگاه واقعی deferred به قبل از فاز ۵ |
| D9 | سرویس SMS | DEC-09 | OPS-05 | resolved: interface + fake (ADR-009)؛ انتخاب provider deferred به قبل از فاز ۵ |
| D10 | ذخیره فایل | DEC-10 | OPS-07 | resolved: interface + fake (ADR-009)؛ انتخاب storage deferred به قبل از فاز ۵ |
| D11 | مالیات در v1 | DEC-11 | — | resolved (ADR-010) |
| D12 | فرمت خطا و 400/422 | DEC-12 | — | resolved (ADR-011) |
| D13 | محیط production | DEC-13 | OPS-04 | deferred به فاز ۵ |
| D14 | واحد پول | — | — | resolved (ADR-001) |
| D15 | مسیرهای API | — | — | resolved (ADR-002) |
| D16 | انتقال refresh token | DEC-16 | — | resolved (ADR-012) |
| D17 | دیتابیس تست و CI | — | — | resolved (ADR-013) |
| D18 | modeهای گردکردن مبلغ | — | — | resolved (ADR-014) |
| D19 | unique روی مدل soft-deletable | — | — | resolved (ADR-015) |

## ADR

### ADR-001 — پول به‌صورت integer تومان (D14)
- تاریخ: 2026-09-29
- زمینه: نقشه راه قدیمی ریال می‌گفت؛ بخش «قیمت و مالیات» تومان.
- تصمیم: همه مبالغ در دیتابیس و API عدد صحیح تومان‌اند؛ float ممنوع؛ گردکردن فقط یک‌بار در pricing service. **تبدیل به ریال فقط داخل adapter درگاه پرداخت.**
- پیامدها: INF-02 و PAY-07.

### ADR-002 — مسیرهای API مطابق PRD (D15)
- تاریخ: 2026-09-29
- تصمیم: مسیرهای بخش‌های مرجع PRD (مثل `/auth/request-otp`) زیر `/api/v1`.
- پیامدها: AUTH-05 تا AUTH-09.

### ADR-003 — Stack فنی (D1)
- تاریخ: 2026-09-29
- تصمیم: stack موجود تأیید شد: Python 3.12، FastAPI، Pydantic v2، SQLAlchemy 2 async + asyncpg، PostgreSQL 16، Alembic، pytest، ruff، mypy strict، Docker Compose.
- پیامدها: تغییر stack نیازمند ADR جدید است.

### ADR-004 — نقش‌ها (D2)
- تاریخ: 2026-09-29
- تصمیم: نقش‌های دیتابیسی `customer`، `support`، `content_manager`، `admin`، `super_admin`. Guest نقش دیتابیسی نیست. `finance_manager` و `warehouse_manager` به نسخه بعد موکول شدند؛ در v1 تنظیمات مالیات/گردکردن با `super_admin` و موجودی با `admin` (مجوز `inventory:update`).
- پیامدها: seed فعلی (`warehouse_manager`) در AUTH-02 اصلاح و `super_admin` اضافه می‌شود. PRD به‌روز شد.

### ADR-005 — مدل موجودی و انبار (D3، D4)
- تاریخ: 2026-09-29
- تصمیم: موجودی فقط در `InventoryItem` به‌ازای (variant، warehouse)؛ ProductVariant ستون موجودی ندارد. v1 یک انبار پیش‌فرض دارد؛ مدل آماده چندانباره.
- پیامدها: CAT-03، INV-01. PRD (بخش‌های «معماری سیستم»، «موجودی و رزرو»، «صفحه اصلی»، «دسته‌بندی محصولات») به‌روز شد.

### ADR-006 — endpoint اعتبارسنجی (D5)
- تاریخ: 2026-09-29
- تصمیم: فقط `POST /checkout/validate` (قیمت، موجودی، تخفیف، ارسال). `/checkout/validate-pricing`، `/cart/items/validate-stock` و `/cart/recalculate` حذف شدند؛ `GET /cart` همیشه محاسبه سرور را برمی‌گرداند.
- پیامدها: ORD-03، CART-03.

### ADR-007 — لحظه رزرو (D6)
- تاریخ: 2026-09-29
- تصمیم: رزرو ۱۵ دقیقه‌ای هنگام `POST /orders`، قبل از `payment init`. رزرو/commit/release endpoint عمومی ندارند: commit در callback موفق، release در شکست، لغو یا انقضا.
- پیامدها: INV-04، ORD-04، PAY-03، PAY-04.

### ADR-008 — رزرو منقضی (D7)
- تاریخ: 2026-09-29
- تصمیم: `409` با `code: RESERVATION_EXPIRED`؛ کد 410 در API استفاده نمی‌شود.
- پیامدها: INF-01، INV-05.

### ADR-009 — providerهای بیرونی (D8، D9، D10)
- تاریخ: 2026-09-29
- تصمیم: درگاه پرداخت، SMS و ذخیره فایل پشت interface با پیاده‌سازی fake برای dev/test. انتخاب provider واقعی قبل از شروع فاز ۵ (DEC-08، DEC-09، DEC-10).
- پیامدها: AUTH-04، CAT-05، PAY-01 مسدود نیستند؛ PAY-07، OPS-05، OPS-07 تا انتخاب واقعی BLOCKED.

### ADR-010 — مالیات (D11)
- تاریخ: 2026-09-29
- تصمیم: مالیات کامل پیاده می‌شود (PricingSetting، taxEnabled روی variant، snapshot) با پیش‌فرض `tax_enabled=false`.
- پیامدها: PRC-01، PRC-02، PRC-05.

### ADR-011 — فرمت خطا و 400/422 (D12)
- تاریخ: 2026-09-29
- تصمیم: شکل `{"error":{"code","message","details"},"request_id"}` حفظ می‌شود. **خطای validation (schema/ورودی) = 400** با `code: VALIDATION_ERROR`؛ **نقض قانون کسب‌وکار = 422** (مثل کد تخفیف غیرقابل‌استفاده، وضعیت نامعتبر سفارش).
- پیامدها: رفتار فعلی repo (validation → 422) در INF-01 به 400 تغییر می‌کند و OpenAPI به‌روز می‌شود.

### ADR-012 — انتقال توکن‌ها (D16)
- تاریخ: 2026-09-29
- تصمیم: نسخه اول فقط وب. refresh token در cookie `HttpOnly; Secure; SameSite=Strict` با Path محدود به مسیرهای auth؛ access token در body. token service مستقل از transport (ساخت/چرخش/ابطال توکن در service؛ خواندن/نوشتن cookie فقط در لایه router).
- **نکته اجرایی:** کاربر `Path=/auth` گفت؛ چون routeها زیر `/api/v1` هستند، مقدار واقعی باید `Path=/api/v1/auth` باشد وگرنه مرورگر cookie را به `/api/v1/auth/refresh` نمی‌فرستد. کاربر در 2026-09-29 `Path=/api/v1/auth` را تأیید کرد.
- پیامدها: AUTH-06 تا AUTH-08؛ CORS با `allow_credentials` (در repo فعال است وقتی wildcard نباشد).

### ADR-013 — دیتابیس تست و CI (D17)
- تاریخ: 2026-09-29
- تصمیم: سرویس `postgres-test` در `docker-compose.yml` با `profiles: ["test"]`؛ CI با GitHub Actions.
- پیامدها: FND-06، FND-07.

### ADR-014 — modeهای گردکردن مبلغ (D18)
- تاریخ: 2026-09-29
- زمینه: PRD («قیمت و مالیات») فقط فیلدهای `roundingMode` و `roundingStep` را نام می‌برد، بدون فهرست modeها.
- تصمیم: سه mode: `up` (ceil)، `down` (floor)، `nearest` (half-up). mode جداگانه `none` وجود ندارد؛ «بدون گردکردن» یعنی `nearest` با `step=1`. پیش‌فرض: `nearest`، `step=1`. مبلغ‌ها نامنفی‌اند؛ تخفیف به‌صورت مبلغ مثبت ذخیره و کم می‌شود.
- پیامدها: INF-02 (`app/shared/money.py`)، PRC-01 (مقدار پیش‌فرض PricingSetting)، PRC-02.

### ADR-015 — unique روی مدل‌های soft-deletable (D19)
- تاریخ: 2026-09-29
- زمینه: INF-04 `SoftDeleteMixin` را اضافه کرد. یک unique کامل مانع می‌شود که مقدار یک رکورد soft-deleted (مثل موبایل، slug یا SKU) دوباره استفاده شود. وضعیت فعلی (read-only): تنها مدل soft-deletable `User` است و `uq_users_phone` یک unique کامل روی `phone` است (partial نیست). unique‌های دیگر (`roles.name`، `permissions.key`، `app_settings.key`) روی مدل‌های غیر soft-deletable هستند.
- تصمیم: فیلد unique روی مدل soft-deletable با partial unique index و شرط `WHERE deleted_at IS NULL` پیاده می‌شود. تصمیم و migration هر مدل در task خود همان مدل گرفته می‌شود (users → AUTH-01، category slug → CAT-01، product slug → CAT-02، SKU → CAT-03). schema فعلی در INF-04 تغییر نکرد.
- پیامدها: AUTH-01، CAT-01، CAT-02، CAT-03. هر task لیست catalog یا public، تست حذف رکورد soft-deleted را در معیار پذیرش دارد (PLAN.md).

### تصمیم‌های deferred
- **D13 — محیط production:** تا فاز ۵ باز است (DEC-13؛ مانع OPS-04).

## PRD changes

| تاریخ | بخش | تغییر | تصمیم مرجع |
|---|---|---|---|
| 2026-09-29 | «معماری سیستم» | ProductVariant بدون موجودی؛ نقش‌های support و content_manager اضافه؛ Finance/Warehouse Manager موکول | D3، D2 |
| 2026-09-29 | «هویت و دسترسی» | نقش‌های support و content_manager؛ refresh در cookie HttpOnly/Secure/SameSite=Strict، access در body | D2، D16 |
| 2026-09-29 | «قیمت و مالیات» | `/cart/recalculate` و `/checkout/validate-pricing` با `POST /checkout/validate` جایگزین شد؛ Finance Manager موکول | D5، D2 |
| 2026-09-29 | «موجودی و رزرو» | رزرو در `POST /orders`؛ endpointهای عمومی reservation و `validate-stock` حذف؛ 410 → 409 `RESERVATION_EXPIRED`؛ یک انبار پیش‌فرض؛ Warehouse Manager موکول | D6، D5، D7، D3، D4، D2 |
| 2026-09-29 | «صفحه اصلی» | موجودی از ProductVariant حذف؛ Content Admin → Content Manager | D3، D2 |
| 2026-09-29 | «دسته‌بندی محصولات» | موجودی از ProductVariant حذف؛ Content Admin → Content Manager | D3، D2 |

قاعده: هر task نوع `XX-00` بخش قالبی ماژول خود را در PRD بازنویسی می‌کند، به عنوان آن بخش «✓ بازبینی‌شده» اضافه می‌کند و یک ردیف به این جدول می‌افزاید.

_قالب ADR جدید:_

```
### ADR-NNN — عنوان (Dn)
- تاریخ: YYYY-MM-DD
- زمینه:
- تصمیم:
- پیامدها:
```
