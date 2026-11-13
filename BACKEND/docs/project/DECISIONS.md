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
| D20 | rate limit و جزئیات request-otp | AUTH-05 | — | resolved (ADR-016) |
| D21 | ورود، session و چرخش refresh | AUTH-06، AUTH-07 | — | resolved (ADR-017) |
| D22 | احراز هویت هر درخواست، permission و مالکیت | AUTH-08، AUTH-09، AUTH-10 | — | resolved (ADR-018) |
| D23 | مدیریت کاربر توسط مدیران (وضعیت و نقش) | AUTH-11 | — | resolved (ADR-019) |
| D24 | نیازمندی‌های محصول (جزئیات و admin) | CAT-00 | — | resolved (ADR-020) |
| D25 | جزئیات schema کاتالوگ (FK، پیش‌فرض، CHECK) | — | — | resolved (ADR-021) |
| D26 | قرارداد API عمومی دسته (`GET /categories`، شکل پاسخ، والد غیرفعال) | — | — | resolved (ADR-022) |
| D27 | دسترسی content_manager به دسته‌ها | — | — | resolved (ADR-023) |
| D28 | مبنای مالیات، تقسیم تخفیف کد و مرحله گردکردن | — | — | resolved (ADR-031) |
| D29 | معنای `PATCH /admin/products/{id}/price` برای محصول چندتنوعی | PRC-03 | — | resolved (ADR-035) |
| D30 | انتقال cart token مهمان | CART-00 | — | resolved (ADR-039) |
| D31 | لحظه شمارش استفاده از کد تخفیف | DSC-00 | — | resolved (ADR-039) |
| D32 | پرداخت موفق بعد از انقضای رزرو | PAY-00 | — | resolved (ADR-039) |
| D33 | کاهش scope فاز ۳ (کد، ارسال، recalculate) | CART-00..PAY-00 | — | resolved (ADR-039) |
| D34 | قواعد جریان خرید (شکست پرداخت، انقضا، rate limit کد، سبد، Idempotency-Key، ارسال رایگان) | CART-00..PAY-00 | — | resolved (ADR-039) |
| D35 | ثبت بازپرداخت دستی (`refunded`) | ADM-00 | — | resolved (ADR-053) |
| D36 | کاهش scope «صفحه اصلی» ✓ | CNT-00 | — | resolved (ADR-053) |
| D37 | حذف حساب کاربر | ACC-00 | ACC-05 | deferred (ADR-053) |
| D38 | موبایل مشتری در پنل و audit مشاهده | ADM-00 | — | resolved (ADR-053) |
| D39 | مرز روز گزارش‌ها (`Asia/Tehran`) | ADM-00 | — | resolved (ADR-053) |
| D40 | قالب محتوای ایستا (Markdown بدون HTML خام) | CNT-00 | — | resolved (ADR-053) |
| D41 | لینک بنر و سکشن فقط داخلی | CNT-00 | — | resolved (ADR-053) |
| D42 | نمونه رنگ (hex) و `is_new` در خلاصه محصول | CAT-18 | — | resolved (ADR-053) |
| D43 | مبلغ بازپرداخت نامعلوم و بازگشت بدهی بعد از بازپرداخت | ADM-08 | — | resolved (ADR-054) |

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
- به‌روزرسانی 2026-10-09 (AUTH-11، کاربر تأیید کرد): admin مجوز `users:manage` را هم دارد. ولی فقط وضعیت کاربرانی را تغییر می‌دهد که همه نقش‌هایشان `customer` است (ADR-019). migration `20261009_0005` ردیف `warehouse_manager` را حذف می‌کند، فقط اگر در `user_roles` ارجاعی نداشته باشد. فقط نقش‌های `DEFAULT_ROLES` قابل تخصیص‌اند.

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
- پیامدها: AUTH-01، CAT-01، CAT-02، CAT-03. SD rule (سرآیند PLAN.md و CLAUDE.md): read عمومی رکورد soft-deleted را برنمی‌گرداند (detail → 404) و write ارجاع‌دهنده آن را رد می‌کند.

### ADR-016 — rate limit و جزئیات `POST /auth/request-otp` (D20)
- تاریخ: 2026-10-06
- زمینه: PRD فقط «محدودیت برای هر شماره و IP → 429» را می‌گوید و عددی ندارد.
- تصمیم (مقادیر را کاربر تأیید کرد): cooldown ارسال مجدد 60s، حداکثر ۵ کد در ساعت برای هر شماره، ۶۰ کد در ساعت برای هر IP (به‌خاطر CGNAT) و سقف سراسری ۵۰۰ کد در ساعت. سقف سراسری برای کنترل هزینه SMS-bombing است و لاگ WARNING `otp.global_cap_hit` دارد. همه به 429 `OTP_RATE_LIMITED` با `Retry-After` ختم می‌شوند. شمارش از `otp_codes` در یک پنجره متحرک ۱ ساعته انجام می‌شود (نام settingها `*_PER_HOUR` است). تصمیم‌های کم‌اثر (خودم): کد قبلی با `expires_at = now` باطل می‌شود و به `consumed_at` دست نمی‌زنیم تا «مصرف» با «ابطال» یکی نشود. SMS بعد از commit ارسال می‌شود. درخواست‌های هر شماره با `pg_advisory_xact_lock` پشت هم اجرا می‌شوند. شمارش per-IP و سراسری lock ندارد و زیر بار همزمان ممکن است کمی از سقف رد شود.
- پیامدها: AUTH-05. شمارش سراسری و per-IP index روی `created_at` ندارد؛ پاک‌سازی دوره‌ای `otp_codes` (task آینده OPS) هزینه آن را محدود می‌کند.

### ADR-017 — ورود با OTP، session و چرخش refresh token (D21)
- تاریخ: 2026-10-06
- زمینه: PRD («هویت و دسترسی») فقط OTP یک‌بارمصرف، access کوتاه‌عمر، refresh بلندعمر و هش‌شده را می‌گوید. رفتار حساب حذف‌شده یا مسدود و جزئیات چرخش در PRD نیامده است.
- تصمیم (کاربر تأیید کرد):
  - verify-otp: ردیف OTP با `FOR UPDATE` قفل می‌شود (به‌علاوه همان advisory lock شماره در ADR-016)، و مقایسه constant-time است. کد اشتباه `attempt_count` را بالا می‌برد. بعد از `OTP_MAX_ATTEMPTS=5` تلاش، کد با `expires_at = now` باطل می‌شود. مصرف کد اتمیک است (`consumed_at IS NULL`). برای کد اشتباه، منقضی، مصرف‌شده یا ناموجود یک خطای یکسان برمی‌گردد: 401 `OTP_INVALID`.
  - اولین ورود: کاربر با نقش `customer` ساخته می‌شود و `mobile_verified_at` مقدار می‌گیرد. audit `auth.login` ثبت می‌شود. حساب `inactive` یا `blocked` → 403 `FORBIDDEN` (کد مصرف می‌شود و token صادر نمی‌شود).
  - حساب soft-deleted هرگز token نمی‌گیرد. اگر حساب حذف‌شده‌ای `active` بوده، verify با همان شماره یک حساب customer جدید می‌سازد (ADR-015). اگر حساب حذف‌شده‌ای با همان شماره `blocked` بوده → 403، تا حذف حساب راه فرار از مسدودی نباشد.
  - tokenها (ADR-012): access یک JWT با HS256 ثابت است (الگوریتم دیگر و `none` رد می‌شوند). claimهای `exp/iat/sub/sid/typ/jti` الزامی‌اند و نقش در آن نیست. `ACCESS_TOKEN_TTL_SECONDS=900`. refresh یک token تصادفی 256 بیتی است که SHA-256 آن در `sessions` ذخیره می‌شود. `REFRESH_TOKEN_TTL_DAYS=30` است و با هر چرخش تمدید می‌شود (sliding). cookie `refresh_token` با `HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth` تنظیم می‌شود.
  - refresh: هر چرخش session قبلی را revoke و session جدیدی در همان `family_id` می‌سازد. ارائه refresh revoke‌شده کل family را revoke می‌کند و audit `auth.refresh_reuse` ثبت می‌شود. grace period وجود ندارد: دو refresh همزمان با یک token هم reuse حساب می‌شوند. کاربر غیرفعال، مسدود یا حذف‌شده نمی‌تواند refresh کند.
- تصمیم‌های کم‌اثر (خودم): SHA-256 ساده برای refresh کافی است، چون token آنتروپی بالا دارد (برخلاف OTP). پاسخ‌های token هدر `Cache-Control: no-store` دارند.
- پیامدها: AUTH-06، AUTH-07، AUTH-08 (logout همین family را revoke می‌کند)، AUTH-10 (وضعیت فعال‌بودن کاربر در هر درخواست از دیتابیس خوانده شود)، DSC-01 (سقف استفاده per-user با موبایل نرمال‌شده، نه `user_id`، چون حذف حساب شماره را آزاد می‌کند)، HANDOFF-01 (frontend باید refresh را در همه تب‌ها single-flight کند، وگرنه reuse detection کاربر را logout می‌کند).
- محدودیت شناخته‌شده: downgrade migration `20261006_0002` یک unique کامل روی `users.phone` برمی‌گرداند و اگر حساب حذف‌شده و حساب جدیدی با یک شماره وجود داشته باشد fail می‌شود.

### ADR-018 — احراز هویت هر درخواست، permission و مالکیت (D22)
- تاریخ: 2026-10-06
- زمینه: PRD فقط می‌گوید «نقش ارسالی از سمت کاربر قابل اعتماد نیست». اینکه access token بعد از logout تا انقضا معتبر بماند یا نه، و اینکه دسترسی به منبع دیگران چه پاسخی بگیرد، در PRD نیامده است.
- تصمیم (کاربر تأیید کرد): `get_current_user` در هر درخواست user و session مربوط به claim `sid` را از دیتابیس می‌خواند. user ناموجود یا soft-deleted، و session revoke‌شده یا منقضی → 401 با `WWW-Authenticate: Bearer`. کاربر `inactive` یا `blocked` → 403. نتیجه: logout و revoke فوراً اثر دارند و بعد از هر refresh، access قبلی هم باطل می‌شود. permissionها از `user_roles → role_permissions` خوانده می‌شوند (اجتماع نقش‌ها) و هیچ claim یا ورودی کلاینت در آن‌ها نقشی ندارد.
- تصمیم‌های کم‌اثر (خودم): `require_permission(key)` کلید ناشناخته را هنگام import با `ValueError` رد می‌کند. `ensure_owner` به‌جای 403 خطای 404 `NOT_FOUND` می‌دهد تا وجود منبع لو نرود. logout با cookie revoke‌شده reuse حساب نمی‌شود (برای idempotent ماندن).
- پروفایل (AUTH-09، کاربر تأیید کرد): email با `email-validator>=2.3,<3.0` و با `check_deliverability=False` اعتبارسنجی و lowercase می‌شود. PATCH با audit `user.profile_updated` ثبت می‌شود و email در diff ماسک می‌شود. پاسخ‌های verify-otp، refresh، logout، `/auth/me` و `/users/me` هدر `Cache-Control: no-store` دارند.
- تصمیم‌های کم‌اثر پروفایل (خودم): نام‌ها در audit ماسک نمی‌شوند (برای کاربرد audit لازم‌اند). `mask_email` فقط اول و آخر local part را نگه می‌دارد. diff روی مقادیر خام ساخته و بعد ماسک می‌شود و هر ردیف `"changed": true` دارد، پس تغییر حتی با ماسک یکسان دیده می‌شود (اصلاح 2026-10-09 به درخواست کاربر؛ برای همه audit ها). body خالی → 200 بدون تغییر. `null` برای نام → 400 و برای email یعنی پاک کردن.
- dependency (کاربر، 2026-10-09): بازه `>=2.3,<3.0` در `pyproject.toml` می‌ماند. نصب قابل‌تکرار با lock file در SEC-06 انجام می‌شود.
- پیامدها: هر درخواست احراز‌شده سه query کوتاه دارد (user+session، roles، permissions). اگر لازم شد، cache در OPS بررسی می‌شود. AUTH-11 هنگام block کردن کاربر نیازی به revoke فوری session ندارد، چون وضعیت در هر درخواست چک می‌شود (هرچند revoke برای refresh مفید است).

### ADR-019 — مدیریت کاربر توسط مدیران: وضعیت و نقش (D23)
- تاریخ: 2026-10-09
- زمینه: PRD («هویت و دسترسی») فقط سه endpoint `GET /admin/users`، `PATCH /admin/users/{id}/status` و `PATCH /admin/users/{id}/role` را نام می‌برد و می‌گوید «تغییر نقش توسط Super Admin». مرز اختیار admin و حفاظت از آخرین super_admin در PRD نیامده است.
- تصمیم (کاربر تأیید کرد):
  - list: مجوز `users:read`. صفحه‌بندی با page و limit (حداکثر 100) است. فقط پارامترهای `page`، `limit`، `mobile`، `status`، `role` و `sort` (`newest` یا `oldest`) پذیرفته می‌شوند و پارامتر دیگر → 400. کاربر soft-deleted در list نمی‌آید.
  - status: مجوز `users:manage` (admin و super_admin). admin فقط وضعیت کاربرانی را تغییر می‌دهد که نقش‌هایشان زیرمجموعه `{customer}` است. هدف با هر نقش staff (support، content_manager، admin، super_admin) فقط توسط super_admin تغییر می‌کند، وگرنه 403. تغییر وضعیت خود → 422. رفتن به `inactive` یا `blocked` همه sessionهای کاربر را revoke می‌کند.
  - role: مجوز `users:manage_roles` و نقش `super_admin` (دو چک جدا). body برابر `{"roles": [...]}` است و کل مجموعه نقش‌ها را جایگزین می‌کند. فقط `DEFAULT_ROLES` پذیرفته می‌شود، یکتا و ۱ تا ۵ نقش؛ در غیر این صورت 400. تغییر نقش خود → 422.
  - آخرین super_admin: اگر تغییری (نقش یا وضعیت) هیچ super_admin فعال و حذف‌نشده‌ای باقی نگذارد → 409 `CONFLICT`. همه این تغییرات با advisory lock `rbac:super_admin` پشت هم اجرا می‌شوند. چون تغییر خود ممنوع است، این حالت فقط در درخواست‌های همزمان پیش می‌آید.
  - audit: `user.status_changed` (status و `revoked_sessions`) و `user.roles_changed` (فهرست مرتب نقش‌ها)، با before/after.
- تصمیم‌های کم‌اثر (خودم): ماژول در `app/modules/admin/` است. تغییری که وضعیت یا نقش را عوض نکند → 200 بدون audit. فعال‌سازی دوباره sessionهای قبلی را برنمی‌گرداند. جست‌وجوی `mobile` رقمی و جزئی است: `+` اختیاری، ۳ تا ۱۶ رقم، و صفر ابتدای شماره محلی حذف می‌شود. کاربر ناموجود یا soft-deleted → 404. پاسخ‌ها هدر `Cache-Control: no-store` دارند. موبایل در پاسخ admin ماسک نمی‌شود، چون admin مجوز `users:read` دارد.
- پیامدها: AUTH-11. seed مجوز `users:manage` را به admin اضافه می‌کند. روی دیتابیس‌های موجود باید `python -m app.db.seed` دوباره اجرا شود.

### ADR-020 — نیازمندی‌های محصول: جزئیات عمومی و مدیریت (D24)
- تاریخ: 2026-10-09
- زمینه: بخش‌های «جزئیات محصول» و «محصولات» (admin) در PRD قالبی بودند. «معماری سیستم» ✓ `GET /products/{id}` را نام می‌برد.
- تصمیم (کاربر تأیید کرد):
  - URL عمومی محصول با slug است (`GET /products/{slug}`) و endpointهای admin با id. `GET /products/{id}/pricing` و `/availability` با id می‌مانند.
  - محصول منتشرشده در دسته غیرفعال: صفحه محصول نمایش داده می‌شود و دسته فقط از breadcrumb حذف می‌شود؛ محصول در لیست آن دسته نمی‌آید.
  - پاسخ جزئیات فیلد صریح `tax_included` دارد (در v1 برابر false). سیاست نمایش قیمت در زمان فعال‌شدن مالیات به D11 (ADR-010) موکول است.
  - media: فقط jpeg/png/webp، حداکثر ۵MB، بدون ویدئو در v1. نوع فایل با magic bytes تشخیص داده می‌شود (نه پسوند یا Content-Type) و EXIF/metadata هنگام بارگذاری حذف می‌شود.
  - `default_variant_id` و `price_range` در پاسخ جزئیات می‌مانند. قاعده SCOPE?: فیلد read-only مشتق از داده موجود می‌ماند و هر feature جدید کاربرمحور حذف می‌شود.
- تصمیم‌های کم‌اثر (خودم): گراف وضعیت draft↔published، published/draft → archived، archived → draft؛ `published_at` فقط در اولین انتشار؛ `discount_percent` به پایین گرد می‌شود و فقط نمایشی است؛ slug را ادمین وارد می‌کند (حروف کوچک لاتین، رقم و `-`، ۳ تا ۱۲۰)؛ SKU به حروف بزرگ نرمال می‌شود؛ گزینه‌های تنوع متن آزاد با کلیدهای color/size/model؛ بدون restore در v1؛ تغییر وضعیت و تغییرات تنوع/رسانه روی ردیف Product قفل می‌گیرند؛ ProductHistory حذف و AuditLog جایگزین شد.
- پیامدها: CAT-02 تا CAT-05، CAT-07، CAT-08، CAT-11، PRC-01 (قانون «تنوع فعال بدون قیمت → 422» بعد از PRC-01). حذف EXIF و تشخیص magic bytes در CAT-05 احتمالاً dependency جدید لازم دارد (مثل Pillow) که در plan آن task با دلیل ذکر می‌شود.

### ADR-021 — جزئیات schema کاتالوگ (D25)
- تاریخ: 2026-10-10
- زمینه: PRD فیلدها را می‌گوید، ولی FK، پیش‌فرض‌ها و CHECKها را نه. همه تصمیم‌ها کم‌اثر و خودم (CLAUDE.md پروتکل ۸).
- تصمیم:
  - Category (CAT-01): soft-deletable (شرط انتشار محصول «دسته soft-delete نشده» را فرض می‌کند). slug همان قاعده slug محصول (`^[a-z0-9-]{3,120}$`) و partial unique (ADR-015). `parent_id` با `ON DELETE RESTRICT` و CHECK `parent_id <> id`؛ چرخه عمیق‌تر در CAT-10. `is_active` پیش‌فرض true.
  - قاعده فرمت slug و SKU علاوه بر API یک CHECK در DB هم دارد (backstop)؛ migration متن literal الگو را کپی می‌کند.
  - همه FKهای بین جدول‌های کاتالوگ `ON DELETE RESTRICT` هستند تا حذف سخت رکورد ارجاع‌شده در DB هم ممکن نباشد. FKهای actor (`created_by`، `updated_by`) به `users` با `SET NULL`، مثل `audit_logs.actor_user_id`.
  - Product (CAT-02): CHECK «`published` ⇒ `published_at` دارد». `published_at` با unpublish پاک نمی‌شود.
  - ProductVariant (CAT-03): `is_active` پیش‌فرض false (تنوع بدون قیمت معتبر نباید فعال باشد؛ قانون 422 بعد از PRC-01)، `is_purchasable` پیش‌فرض true. SKU سراسری یکتا (نه per product) و CHECK روی شکل نرمال‌شده.
  - VariantOption و ProductAttribute (CAT-04): unique `(variant_id, option_key)` و `(product_id, attribute_key)`؛ یعنی هر کلید ویژگی در هر محصول یک مقدار دارد (PRD این را برای ویژگی صریح نمی‌گوید). طول کلید ویژگی ۵۰ و مقدار ۲۰۰ کاراکتر. بدون timestamp (تغییرات در AuditLog).
- پیامدها: CAT-01، CAT-02، CAT-03، CAT-04، CAT-06، CAT-10، CAT-11، PRC-01.

### ADR-022 — API عمومی دسته‌بندی (D26)
- تاریخ: 2026-10-10
- تصمیم (کاربر تأیید کرد): `GET /categories` یک درخت از دسته‌های قابل نمایش برمی‌گرداند. `GET /categories/{slug}` فیلدهای دسته، breadcrumb و زیرمجموعه‌های قابل نمایش را برمی‌گرداند. «قابل نمایش» یعنی دسته و **همه** اجدادش فعال و soft-delete‌نشده باشند؛ وگرنه دسته از درخت حذف می‌شود و detail آن 404 `NOT_FOUND` می‌دهد. `GET /categories` به بخش «دسته‌بندی محصولات» PRD اضافه شد.
- پیامدها: CAT-06؛ لیست محصولات دسته (CAT-07) همین قاعده را برای دسته به کار می‌برد.

### ADR-023 — مجوز ویرایش محتوای دسته (D27)
- تاریخ: 2026-10-10
- تصمیم (کاربر تأیید کرد): مجوز جدید `categories:edit_content` برای content_manager (و طبق قاعده موجود برای admin و super_admin). این مجوز فقط `title`، `description`، بنر (`image_url`) و ترتیب (`display_order`) را ویرایش می‌کند. ساختار (ایجاد، حذف، `parent_id`، `slug`، `is_active`) فقط با `catalog:manage`. هر دو مسیر تست می‌شوند. CAT-10 به Level HIGH رفت (تغییر RBAC).
- تصمیم کم‌اثر (خودم): `icon_key` و فیلدهای seo جزو ساختار نیستند ولی چون کاربر فقط چهار فیلد را نام برد، فعلاً فقط با `catalog:manage` ویرایش می‌شوند.
- پیامدها: CAT-10، seed RBAC (AUTH-02).

### ADR-024 — Pillow برای رسانه (CAT-05)
- تاریخ: 2026-10-10
- تصمیم (کاربر تأیید کرد): Pillow از طریق lock (SEC-06) اضافه می‌شود. `Image.MAX_IMAGE_PIXELS` تنظیم می‌شود، ابعاد قبل از decode کامل (از header) بررسی می‌شود، و هر فایل هنگام بارگذاری re-encode می‌شود تا EXIF و metadata حذف و فایل‌های polyglot خنثی شوند.
- پیامدها: CAT-05.

### ADR-025 — قواعد مدیریت دسته (CAT-10)
- تاریخ: 2026-10-10
- تصمیم (کاربر تأیید کرد):
  - `DELETE /admin/categories/{id}` حذف نرم انجام می‌دهد و فقط با `catalog:manage` مجاز است. دسته‌ای که زیرمجموعه یا محصول حذف‌نشده دارد → 409.
  - `image_url` فقط `https` و فقط روی hostهای `MEDIA_ALLOWED_HOSTS` پذیرفته می‌شود، بدون user info و port؛ وگرنه 400. در CAT-05 این فیلد با `media_id` جایگزین می‌شود.
  - حداکثر عمق درخت دسته ۵ سطح است (PRD مقداری تعیین نکرده)؛ تجاوز از آن → 422.
- تصمیم‌های کم‌اثر (خودم):
  - parent ناموجود یا حذف‌شده → 422 و چرخه → 409.
  - همه نوشتن‌های دسته با یک advisory lock تراکنشی سریال می‌شوند تا دو جابه‌جایی همزمان نتوانند چرخه بسازند.
  - مرز مجوز روی فیلدهای ارسال‌شده (نه فقط تغییرکرده) بررسی می‌شود.
  - لیست ادمین دسته‌های غیرفعال را نشان می‌دهد، soft-deleted را نه، با sort `display_order` (پیش‌فرض) یا `newest`.
- پیامدها: CAT-10؛ CAT-05 (جایگزینی `image_url` با `media_id`)؛ `.env.example`.

### ADR-026 — فیلترهای دسته (CAT-09)
- تاریخ: 2026-10-10
- تصمیم‌های کم‌اثر (خودم):
  - `attribute_key` یکی از این‌هاست: کلید گزینه تنوع (color/size/model، مقدار از تنوع‌های فعال)، کلید ProductAttribute، یا `price`. نوع `range` فقط برای `price` و `color` فقط برای کلید `color` است.
  - مقدار و تعداد فقط از محصولات published و حذف‌نشده خود دسته می‌آیند (بدون زیرمجموعه‌ها). فیلتر بدون مقدار در خروجی عمومی نمی‌آید.
  - فیلتر `price` تا CAT-07 داده ندارد. CAT-07 min/max قیمت نهایی را اضافه می‌کند.
  - مدیریت با `catalog:manage`، جایگزینی کل مجموعه (حداکثر ۳۰)، audit `category.filters_updated`. مجموعه یکسان → بدون audit.
- پیامدها: CAT-09، CAT-07.

### ADR-027 — schema قیمت (PRC-01)
- تاریخ: 2026-10-10
- تصمیم‌های کم‌اثر (خودم؛ بازبینی subagent):
  - variant: `base_price`/`sale_price` از نوع BIGINT تومان و nullable. NULL یعنی «هنوز قیمت ندارد». سقف قیمت `MAX_PRICE_TOMAN = 10^12`. `1 ≤ sale ≤ base`. بازه sale معتبر است و فقط وقتی sale_price وجود دارد. CHECK backstop: «تنوع فعال باید `base_price` داشته باشد».
  - `price_version` با هر تغییر قیمت variant بالا می‌رود. `pricing_settings.version` با هر تغییر تنظیمات (PRC-05) بالا می‌رود. checkout و PRC-02 هر دو را fingerprint می‌کنند تا تغییر مالیات یا گردکردن هم `PRICE_CHANGED` حساب شود.
  - `pricing_settings` یک ردیف singleton است (`singleton` unique با CHECK) و migration آن را با id ثابت uuid5 درج می‌کند. ستون `currency` فقط `TOMAN` می‌پذیرد. نرخ مالیات به basis points (`0..10000`) است، نه float. `rounding_step` بین 1 و `10^6`. `updated_by` با `SET NULL`.
  - در v1 نرخ مالیات per-variant وجود ندارد: فقط `tax_enabled` روی variant و `default_tax_rate_bps` سراسری (PRD entities). `taxRate` ورودی PRD همان نرخ سراسری است.
  - migration: variant فعال بدون قیمت غیرفعال می‌شود و تعداد آن log می‌شود. اگر چنین variantی متعلق به محصول published باشد، migration با خطا متوقف می‌شود تا محصول منتشرشده بی‌تنوع فعال نماند. downgrade قیمت‌ها را حذف می‌کند و `is_active` را برنمی‌گرداند.
  - API قیمت (CAT-11، PRC-03) باید `ge=1` و `le=MAX_PRICE_TOMAN` را اعمال کند (`Toman` فقط `ge=0` دارد).
- پیامدها: PRC-01، PRC-02، PRC-03، PRC-05، CAT-11، ORD-03.

### ADR-028 — رسانه و آپلود (CAT-05)
- تاریخ: 2026-10-10
- تصمیم (کاربر تأیید کرد: گزینه الف و M2.2-PLAN.md):
  - dependencyها: `python-multipart` 0.0.32 و `pillow` 12.3 از طریق lock با hash.
  - سقف حجم هنگام stream اعمال می‌شود: Content-Length بزرگ‌تر از `MAX_REQUEST_BYTES` و stream بدون Content-Length هر دو قبل از خواندن کامل body رد می‌شوند. حداکثر یک فایل و تعداد محدود فیلد. فایل‌ها در temp file روی دیسک spool و همیشه بسته می‌شوند.
  - جدول عمومی `media` (storage_key، content_type، size_bytes، width، height) و `product_media` با `media_id` (unique). این از entity داخلی PRD فاصله دارد تا بنر دسته و بعداً بنر محتوا از همان رسانه استفاده کنند. `categories.image_url` با `image_media_id` جایگزین شد (ADR-025) و پاسخ‌ها `image_url` ساخته‌شده توسط سرور را دارند. endpoint `POST /admin/media` با `catalog:manage` یا `categories:edit_content` و audit `media.uploaded`. آپلود تصویر محصول در CAT-11 (`POST /admin/products/{id}/media`) است.
- تصمیم‌های کم‌اثر (خودم؛ بازبینی subagent):
  - `MAX_UPLOAD_BYTES = 5 MiB = 5_242_880` و `MAX_REQUEST_BYTES` = همان + 64 KiB.
  - حداکثر ابعاد ۶۰۰۰px در هر ضلع و ۳۶M پیکسل. این ابعاد از header بررسی می‌شوند، قبل از decode، و `DecompressionBombWarning` به خطا تبدیل می‌شود.
  - حداکثر ۲ decode همزمان (CapacityLimiter). تصویر animated رد می‌شود.
  - re-encode از pixel خام، پس exif، xmp، icc، comment و text chunk حذف می‌شوند. orientation قبل از حذف اعمال می‌شود. فایل ذخیره‌شده حداکثر ۴ برابر سقف آپلود است.
  - `MEDIA_ALLOWED_HOSTS` می‌ماند و host `MEDIA_PUBLIC_BASE_URL` باید در آن باشد. production فقط https و storage غیر `memory` می‌پذیرد.
  - کلید را سرور می‌سازد (uuid hex + پسوند) و regex و resolve زیر root بررسی می‌شوند. نوشتن اتمیک با temp در همان پوشه انجام می‌شود. `/media` فقط در development و با `nosniff` mount می‌شود.
  - اگر نوشتن DB شکست بخورد یا درخواست cancel شود، فایل ذخیره‌شده حذف می‌شود. فایل‌ها و ردیف‌های یتیم در crash window → task پاک‌سازی OPS.
  - composite FK `(variant_id, product_id)` تضمین می‌کند تنوع رسانه از همان محصول باشد.
- پیامدها: CAT-05، CAT-11 (آپلود، حذف رسانه و فایل بعد از commit)، CNT-03، OPS-07.

### ADR-029 — مدل موجودی و وضعیت موجودی (INV-01، INV-03)
- تاریخ: 2026-10-10
- تصمیم‌های کم‌اثر (خودم؛ بازبینی subagent):
  - `inventory_items.reserved_quantity` (Entity PRD ✓) شمارنده رزروهای فعال است. invariant: `reserved_quantity == SUM(quantity)` آیتم‌های رزرو با status `active`. INV-04 تا INV-06 آن را فقط زیر `SELECT … FOR UPDATE` تغییر می‌دهند و یک تست invariant دارند.
  - (جایگزین‌شده با ADR-036: رزرو منقضی هیچ موجودی‌ای نگه نمی‌دارد.) رزرو منقضی تا آزادسازی هنوز موجودی را اشغال می‌کند (جهت محافظه‌کارانه؛ oversell ممکن نیست). هر مسیر نوشتنی (سبد، `POST /checkout/validate`، `POST /orders`) قبل از محاسبه free، رزروهای منقضی همان آیتم‌ها را زیر همان lock آزاد می‌کند (PRD: «در اولین بررسی آزاد شود»)، به‌علاوه sweep دوره‌ای (INV-06). نمایش فقط‌خواندنی ممکن است کمی کهنه باشد، فقط در جهت کمتر.
  - ترتیب lock: سفارش چندتنوعی ردیف‌های `inventory_items` را با `ORDER BY variant_id, warehouse_id … FOR UPDATE` قفل می‌کند تا deadlock رخ ندهد.
  - CHECKهای `0 ≤ reserved ≤ total ≤ MAX_STOCK_QUANTITY (10^6)` فقط backstop هستند. سرویس‌ها (INV-02، INV-05، INV-08) شرط را زیر lock بررسی می‌کنند و 409 (موجودی کافی نیست) یا 422 برمی‌گردانند، نه 500. commit رزرو `total` و `reserved` را در یک UPDATE کم می‌کند.
  - وضعیت: `free = total − reserved`؛ `free == 0` → `out_of_stock`؛ `free ≤ low_stock_threshold` → `low_stock`؛ وگرنه `in_stock`. پیش‌فرض threshold صفر است، یعنی `low_stock` تا تنظیم ادمین نمایش داده نمی‌شود. تنوع بدون InventoryItem → `out_of_stock`. داده ناسازگار (منفی یا reserved > total) → `ValueError`.
  - چند انبار (آماده برای بعد از v1): فراخواننده فقط آیتم‌های انبارهای فعال را می‌دهد و total، reserved و threshold جمع می‌شوند. وضعیت کلی محصول بهترین وضعیت بین تنوع‌هایی است که فراخواننده می‌دهد (in > low > out)؛ بدون تنوع → out. عدد موجودی فقط داخلی یا admin است و در پاسخ عمومی نمی‌آید (CAT-00 ردیف ۸).
  - انبار پیش‌فرض با id ثابت uuid5 از migration می‌آید، partial unique دارد و باید فعال باشد. task مدیریت انبار در آینده نباید اجازه حذف یا برداشتن پیش‌فرض را بدهد.
- پیامدها: INV-01، INV-02، INV-03، INV-04 تا INV-08، CAT-07، CAT-08، CAT-11.

### ADR-030 — مدیریت محصول، تنوع و رسانه محصول (CAT-11)
- تاریخ: 2026-10-10
- تصمیم‌های کم‌اثر (خودم؛ بازبینی subagent):
  - فیلدهای سیستمی شناخته‌شده (`id`، `status` در ایجاد، `published_at`، `created_by`، `updated_by`، timestamps، `deleted_at`، `price_version`، `tax_enabled`، فیلدهای موجودی) قبل از validation حذف و نادیده گرفته می‌شوند. هر کلید ناشناخته دیگر → 400. در `PATCH /admin/products/{id}` فیلد `status` رد می‌شود (400) چون endpoint جدا دارد. فیلدهای قیمت در `PATCH /admin/product-variants/{id}` نادیده گرفته می‌شوند (PRD: «قیمت خارج از ایجاد تنوع»).
  - مجوز `pricing:update` روی فیلدهای قیمت ارسال‌شده بررسی می‌شود، حتی با مقدار null (ADR-025). validation بدنه (400) قبل از این 403 اجرا می‌شود.
  - دسته ناموجود یا حذف‌شده در بدنه محصول → 404 (فهرست خطای PRD). ایجاد محصول، تغییر دسته و انتشار، ردیف دسته را `FOR SHARE` می‌گیرند تا با حذف همزمان دسته (CAT-10، `FOR UPDATE`) سریال شوند.
  - ترتیب lock: Product (`FOR UPDATE`) → دسته (`FOR SHARE`) → تنوع/رسانه. PRC-03 هم باید اول Product را lock کند و نباید `base_price` تنوع فعال را پاک کند.
  - `publish_blockers`: `category_missing`، `no_active_priced_variant`، `no_main_image`. خطای 422 انتشار همین کدها را با پیام در `details` دارد.
  - حذف محصول یک ردیف audit `product.deleted` با `variant_ids` دارد. رسانه و فایل‌های محصول حذف‌شده باقی می‌مانند.
  - حذف تنوع `variant_id` رسانه‌های آن را null می‌کند (رسانه روی محصول می‌ماند) و شناسه‌ها در audit می‌آیند.
  - تصویر اصلی: برداشتن `is_main` → 422 (به‌جای آن تصویر دیگری اصلی می‌شود). حذف تصویر اصلی فقط وقتی مجاز است که تنها تصویر محصول باشد و محصول published نباشد. IntegrityError ایندکس `uq_product_media_main` → 409.
  - ترکیب گزینه‌ها بعد از trim و حساس به حروف مقایسه می‌شود («Red» و «red» متفاوت‌اند)، فقط بین تنوع‌های حذف‌نشده. تنوع بدون گزینه همان ترکیب خالی است.
  - لیست admin: `newest`/`oldest` بر اساس `created_at` (پیش‌نویس `published_at` ندارد) و `title`، همه با tie-break `id`. `q` بعد از trim خالی → 400. جست‌وجوی SKU با `EXISTS` (بدون تکرار ردیف). `price_range` روی `base_price` تنوع‌های فعال است (قیمت نهایی در PRC-02).
  - موجودی جزئیات admin فقط از انبارهای فعال (ADR-029)، با اعداد کامل (admin).
  - PATCH با بدنه‌ای که بعد از حذف فیلدهای سیستمی/قیمت خالی می‌ماند → 400 «at least one field»؛ بدنه با مقادیر برابر مقدار فعلی → 200 بدون audit. `alt_text` خالی null ذخیره می‌شود.
  - لیست admin عنوان دسته soft-deleted را هم نشان می‌دهد (نمای مدیریت)؛ جزئیات آن را با `category_missing` علامت می‌زند.
  - حذف فایل در storage best-effort است (shielded؛ شکست فقط log و فایل یتیم برای پاک‌سازی OPS).
- پیامدها: CAT-11، CAT-07، CAT-08، PRC-03.

### ADR-031 — محاسبه قیمت سفارش: مبنای مالیات، تقسیم و گردکردن (D28)
- تاریخ: 2026-10-11
- تصمیم (کاربر تأیید کرد):
  - مبنای مالیات: خطوط مشمول (variant با `tax_enabled` و مالیات فعال در PricingSetting)، بعد از تخفیف محصول و بعد از سهم تقسیم‌شده تخفیف کد. هزینه ارسال مالیات ندارد؛ سیاست مالیات ارسال به D11 (ADR-010) موکول است.
  - هر جزء محاسبه‌شده یک‌بار گرد می‌شود و `grand_total` = جمع اجزای گردشده است.
  - تقسیم تخفیف کد و مالیات بین خطوط با largest-remainder و tie-break قطعی به ترتیب خطوط.
  - guardها: تخفیف کد ≤ جمع مشمول کد؛ `grand_total ≥ 0`؛ تست invariant روی حداقل ۱۰۰۰ سبد تصادفی با seed (stdlib `random`): جمع خطوط = جمع کل، بدون مقدار منفی، ورودی یکسان → خروجی یکسان.
- تصمیم‌های کم‌اثر (خودم؛ بازبینی subagent):
  - «جزء محاسبه‌شده» یعنی تخفیف کد درصدی و مالیات. قیمت‌های واحد، مبلغ ثابت کد و هزینه ارسال عدد صحیح‌اند و گرد نمی‌شوند، تا مبلغی که ادمین تعیین کرده تغییر نکند. `grand_total` لزوماً مضرب step نیست.
  - تخفیف کد بعد از گردکردن به `min(سقف کد، جمع مشمول)` محدود می‌شود (mode `up` از هیچ‌کدام بیشتر نمی‌شود). کدی که هیچ خط مشمولی ندارد مبلغ 0 و `code_applied = false` دارد؛ DSC/ORD برای آن 422 می‌دهند.
  - mode `up` با step بزرگ می‌تواند مالیات خط کوچک را تا یک step بالا ببرد؛ این نتیجه سیاست تنظیم‌شده است (تست مستند).
  - ترتیب خطوط برای tie-break همان ترتیبی است که فراخواننده می‌دهد؛ قرارداد: ترتیب پایدار (مثلاً زمان ایجاد آیتم سبد، سپس id) تا یک سبد همیشه یک تقسیم داشته باشد.
  - بازه sale نیمه‌باز `[start, end)`؛ ابتدای خالی یعنی از قبل، انتهای خالی یعنی باز. `discount_percent` نمایشی و با floor (PRD).
  - `fingerprint` = sha256 روی JSON مرتب از (`key`، `price_version`، قیمت اصلی، قیمت نهایی، `tax_enabled`) هر خط و `pricing_settings.version`، تا شروع یا پایان بازه sale هم `PRICE_CHANGED` شود.
  - نگاشت OrderItem: `unitPrice = original`، `discountAmount = product_discount + code_discount`، `taxAmount = tax`، `finalLineTotal = total`. خروجی `currency` و `calculated_at` هم دارد. سبد خالی → صفر به‌علاوه shipping ورودی.
  - guardها: قیمت ≤ `MAX_PRICE_TOMAN`، تعداد ≤ `MAX_STOCK_QUANTITY`، بازه sale معتبر، policy با نوع درست (`RoundingMode`، bool)، و هر مبلغ خروجی در BIGINT؛ وگرنه `TypeError`/`ValueError`.
- به‌روزرسانی 2026-10-11 (تصمیم کاربر): هر task از CART-* و ORD-* که تابع قیمت را صدا می‌زند (اکنون CART-03، ORD-03، ORD-04) خطوط را با ترتیب پایدار (بر اساس id خط) می‌دهد و یک تست دارد که ورودی با ترتیب به‌هم‌ریخته خروجی یکسان می‌دهد. این معیار در PLAN آن taskها ثبت شد و هنگام ساخت فایل task به Acceptance Criteria منتقل می‌شود.
- پیامدها: PRC-02، CAT-07، CAT-08، CART، ORD-03، ORD-04، DSC.

### ADR-032 — لیست عمومی محصولات (CAT-07)
- تاریخ: 2026-10-11
- زمینه: PRD ورودی‌های لیست را نام می‌برد ولی شکل پارامتر، معنای قیمت محصول چندتنوعی و شکل پاسخ را نه. همه تصمیم‌ها کم‌اثر و خودم (CLAUDE.md پروتکل ۸).
- تصمیم‌های کم‌اثر (خودم):
  - endpointها: `GET /categories/{slug}/products` و `GET /products` (با `category_slug` اختیاری)، با پارامترهای یکسان. پاسخ فقط صفحه کارت‌هاست (`items`، `total`، `page`، `limit`، `pages`). اطلاعات دسته، زیرمجموعه‌ها و فیلترها از `GET /categories/{slug}` و `/filters` می‌آیند.
  - «تنوع عمومی» = فعال، قیمت‌دار و حذف‌نشده. محصول بدون تنوع عمومی در لیست نمی‌آید. **قیمت لیست** محصول = کمترین `final_price` تنوع‌های عمومی در لحظه درخواست (بازه sale نیمه‌باز، همان `unit_price`). فیلتر قیمت، sortهای قیمت و `min`/`max` فیلتر `price` در `/filters` همه روی همین عدد هستند.
  - کارت: `price` (قیمت کامل تنوع ارزان‌تر؛ در تساوی، `display_order` کمتر)، `price_range` روی final، `max_discount_percent` (بیشترین درصد تخفیف فعلی، floor)، `availability` (بهترین وضعیت، ADR-029)، `image_url` تصویر اصلی، و `quick_add_variant_id` (فقط وقتی محصول دقیقاً یک تنوع عمومی دارد و قابل خرید است؛ وگرنه null یعنی «انتخاب تنوع لازم است»).
  - sortها: `newest` (پیش‌فرض، `published_at` نزولی)، `price_asc` و `price_desc` (قیمت لیست)، `discount_desc` (`max_discount_percent`، سپس newest). همه با tie-break نهایی `id`. `best_selling` تا CAT-17 → 400.
  - فیلترها: `min_price`/`max_price` (`0..MAX_PRICE_TOMAN`؛ min > max → 400)، `in_stock` (حداقل یک تنوع عمومی با free > 0 در انبار فعال)، `has_discount` (حداقل یک تنوع با final < base). مقدار `false` یعنی بدون محدودیت. فیلتر ویژگی: `colors`، `sizes`، `materials`، `brands` (پارامتر تکراری؛ کلیدهای color، size، material، brand) و `attributes=key:value` برای هر کلید دیگر. کلید گزینه تنوع روی تنوع‌های عمومی و بقیه روی ProductAttribute تطبیق می‌شوند. مقادیر یک کلید OR و کلیدهای مختلف AND هستند (هر کلید مستقل، نه لزوماً روی یک تنوع؛ همان مبنای شمارش‌های `/filters`).
  - سقف‌ها: حداکثر ۲۰ مقدار برای هر پارامتر، مقدار ۱ تا ۲۰۰ و کلید ۱ تا ۵۰ کاراکتر؛ تخطی → 400. page و limit طبق INF-03.
  - سازگاری با دسته: در لیست دسته (هر دو مسیر)، کلید ویژگی‌ای که در CategoryFilterهای فعال دسته نیست → 422 `BUSINESS_RULE_VIOLATION` با `type: filter_not_applicable`. قیمت، موجودی و تخفیف همیشه مجازند. `GET /products` بدون دسته هر کلیدی را می‌پذیرد.
  - دسته پنهان یا ناموجود → 404 (ADR-022). slug نامعتبر در مسیر → 404 (مثل بقیه endpointهای دسته) و در `category_slug` → 400 (validation پارامتر). محصولات زیرمجموعه‌ها در لیست دسته نمی‌آیند (همان قاعده ADR-026). محصول منتشرشده در دسته پنهان در `GET /products` بدون دسته می‌آید، چون صفحه‌اش عمومی است (ADR-020).
  - اولویت محصولات ویژه (`is_featured`) در v1 اعمال نمی‌شود: PRD آن را مشروط به «سیاست نمایش فعال» کرده و چنین تنظیمی وجود ندارد. جست‌وجوی متنی (`q`) مال بخش «جست‌وجو» است. وضعیت علاقه‌مندی با ماژول wishlist اضافه می‌شود.
  - بدون migration: indexهای موجود `products (status, published_at)` و `products (category_id)` و `product_variants (product_id, display_order)` کافی‌اند. count و صفحه دو query هستند (helper مشترک `paginate`) و کل پاسخ تعداد query ثابت دارد.
  - `Cache-Control: no-store` (قیمت و موجودی هر درخواست تازه، مثل CAT-08).
- پیامدها: CAT-07، CAT-09 (`min`/`max` فیلتر `price`)، CAT-17، SRCH، WISH.

### ADR-033 — قیمت و موجودی عمومی محصول و تنظیمات قیمت (PRC-04، PRC-05، INV-07)
- تاریخ: 2026-10-11
- زمینه: PRD شکل پاسخ `GET /products/{id}/pricing`، `GET /products/{id}/availability` و تنظیمات قیمت را تعیین نکرده است. همه تصمیم‌ها کم‌اثر و خودم (بازبینی subagent).
- تصمیم‌های کم‌اثر (خودم):
  - هر دو endpoint عمومی با id محصول (ADR-020) و `variant_id` اختیاری هستند. فقط محصول published و حذف‌نشده و فقط تنوع‌های عمومی (فعال، قیمت‌دار، حذف‌نشده؛ همان مجموعه CAT-07/CAT-08) برمی‌گردند. محصول پنهان → 404 یکسان. `variant_id` که تنوع عمومی همان محصول نیست → 404. id غیر UUID → 400. `Cache-Control: no-store` روی پاسخ موفق (مثل CAT-07/CAT-08).
  - pricing: `product_id`، `currency` (TOMAN)، `tax_included` (false، ADR-010/D11)، `calculated_at` (لحظه محاسبه، «timestamp محاسبه» PRD؛ `price_version` عمومی نیست)، `price_range` و برای هر تنوع `variant_id`، `sku` و `price` (همان شکل جزئیات).
  - availability: `product_id`، `availability` (بهترین وضعیت، ADR-029) و برای هر تنوع `variant_id`، `sku`، `availability` و `purchasable`. «حداکثر تعداد قابل خرید» خروجی PRD عملاً همان موجودی آزاد است، پس در پاسخ عمومی نمی‌آید (ADR-029، CAT-00 ردیف ۸). سقف تعداد در سبد و checkout (CART، `POST /checkout/validate`) اعمال و با 409 اعلام می‌شود. خواندن بدون lock است (ADR-029). با `variant_id`، وضعیت کلی همان وضعیت تنوع انتخاب‌شده است.
  - تنظیمات: `GET` و `PATCH /admin/pricing/settings` هر دو با `pricing_settings:update` (در v1 فقط super_admin). مجوز خواندن جدا وجود ندارد؛ نقش مالی آینده باید مجوز خواندن جدا بگیرد تا دسترسی نوشتن را به ارث نبرد. فیلدهای قابل تغییر: `tax_enabled`، `default_tax_rate_bps` (`0..10000`)، `rounding_mode`، `rounding_step` (`1..10^6`)، با نوع strict (float، رشته یا bool جای عدد → 400). `id`، `currency`، `version`، `updated_by`، `updated_at` و `singleton` فیلد سیستمی‌اند و نادیده گرفته می‌شوند. بدنه‌ای که بعد از حذف آن‌ها خالی بماند → 400. تغییر → `version + 1`، `updated_by` و audit `pricing.settings_updated` در همان تراکنش، زیر `FOR UPDATE` ردیف singleton. بدون تغییر → 200 بدون audit و bump. نبود ردیف → 404.
  - `tax_enabled = true` با نرخ 0 مجاز است. در v1 هیچ API‌ای `tax_enabled` تنوع را تنظیم نمی‌کند (ADR-030)، پس فعال‌کردن مالیات هنوز روی قیمت‌ها اثری ندارد. این در توضیح پاسخ آمده است.
  - repository تنظیمات یک `PricingPolicy` با `RoundingMode` واقعی می‌سازد، برای CART-03 و ORD-03.
- پیامدها: PRC-04، PRC-05، INV-07، CART-03، ORD-03، PRC-06.

### ADR-034 — InventoryMovement و اصلاح دستی موجودی (INV-02)
- تاریخ: 2026-10-11
- تصمیم‌های کم‌اثر (خودم؛ بازبینی subagent):
  - هر تغییر شمارنده‌های InventoryItem یک ردیف `inventory_movements` در همان تراکنش و زیر همان lock دارد: `movement_type`، `quantity` = |تغییر| (همیشه > 0؛ correction به مقدار مطلق هم |after − before| ذخیره می‌کند)، و هر دو طرف (`total_before/after`، `reserved_before/after`). CHECKها سازگاری هر نوع را تضمین می‌کنند: increase/return فقط total را +q، decrease −q، correction فقط total، reserve/release فقط reserved را ±q، commit هر دو را −q. reserve/release/commit مرجع اجباری دارند (`reference_type` از allowlist: reservation، order، payment، return). increase/decrease/correction دلیل اجباری دارند (۱..۵۰۰ کاراکتر بعد از trim).
  - اصلاح دستی (سرویس داخلی؛ endpoint در INV-08): فقط در انبار پیش‌فرض. InventoryItem نبود → با `INSERT … ON CONFLICT DO NOTHING` ساخته می‌شود. increase بیش از `MAX_STOCK_QUANTITY` → 422. decrease یا correction زیر reserved → 409 `INSUFFICIENT_STOCK`. correction به مقدار فعلی → no-op بدون movement و audit. مقدار غیر int (از جمله bool) یا خارج از بازه و دلیل خالی → 400. variant ناموجود یا حذف‌شده → 404.
  - ترتیب lock برای هر نوشتن موجودی: variant (`FOR SHARE`، تا با حذف نرم همزمان CAT-11 سریال شود) → inventory_item (`FOR UPDATE`؛ چند آیتم به ترتیب `variant_id, warehouse_id`، ADR-029). ردیف Product قفل نمی‌شود. INV-04..06 همین ترتیب را رعایت می‌کنند. فقط اصلاح دستی InventoryItem می‌سازد؛ مسیرهای رزرو آیتم ناموجود را «ناموجود» حساب می‌کنند و آیتم نمی‌سازند.
  - audit `inventory.adjusted` روی `inventory_item` با total قبل و بعد، نوع، دلیل و شناسه movement. actor خالی → `actor: system` (برای job انقضا).
- پیامدها: INV-02، INV-04..06، INV-08.

### ADR-035 — تغییر قیمت و PriceHistory (PRC-03، D29)
- تاریخ: 2026-10-12
- تصمیم (کاربر تأیید کرد، D29 گزینه الف): `PATCH /admin/products/{id}/price` فقط برای محصولی که دقیقاً یک تنوع حذف‌نشده دارد (فعال یا غیرفعال) روی همان تنوع اعمال می‌شود؛ وگرنه 422 `multiple_variants`. تغییر دسته‌جمعی قیمت در v1 نیست. تغییر قیمت هر تنوع با `PATCH /admin/product-variants/{id}/price` (مسیر PRD، هم‌خانواده routeهای موجود)؛ همان مجوز `pricing:update`، history و audit.
- تصمیم‌های کم‌اثر (خودم؛ بازبینی subagent):
  - `price_history`: هر دو طرف base، sale و بازه sale، `reason` (اختیاری، ۱..۵۰۰)، `changed_by` (SET NULL)؛ قیمت‌ها BIGINT با CHECK بازه؛ `new_base_price` NOT NULL؛ `old_*` برای اولین قیمت NULL است. ایجاد تنوع با قیمت اولیه (CAT-11) هم یک ردیف history می‌نویسد. FK مرکب `(variant_id, product_id)`.
  - بدنه: فیلدهای فرستاده‌شده تغییر می‌کنند و بقیه می‌مانند. حداقل یک فیلد قیمت لازم است (فقط `reason` → 400). خطاهایی که فقط به بدنه وابسته‌اند (null برای base، نوع غیر strict، sale > base هر دو در بدنه، بازه معکوس، زمان بدون timezone، کلید ناشناخته) → 400. تعارض با مقدار ذخیره‌شده (base جدید کمتر از sale فعلی، بازه بدون sale، sale روی تنوع بدون base) → 422 با `details.type`. حذف `sale_price` بازه را هم پاک می‌کند. فیلدهای سیستمی (`price_version`، `tax_enabled`، …) نادیده گرفته می‌شوند.
  - lock: Product (`FOR UPDATE`) سپس تنوع (ADR-030)؛ تعداد تنوع‌های endpoint محصول زیر همان lock شمرده می‌شود. بدون تغییر → 200 بدون history، audit و bump. با تغییر: `price_version + 1`، یک ردیف history و audit `product_variant.price_changed` در همان تراکنش. `Cache-Control: no-store`.
  - تاریخچه: `GET /admin/products/{id}/price-history` با `pricing:update` یا `catalog:manage`، جدیدترین اول بر اساس ستون identity `seq` (ترتیب درج؛ مستقل از دقت ساعت)؛ محصول حذف‌شده هم قابل مشاهده است.
- پیامدها: PRC-03، CAT-11، PRC-06.

### ADR-036 — رزرو موجودی: schema، reserve و انقضای مستقل از job (INV-04..06)
- تاریخ: 2026-10-12
- تصمیم (کاربر تأیید کرد): رزرو در `POST /orders` با TTL ۱۵ دقیقه (ADR-007). حداکثر یک رزرو active برای هر سفارش. رزرو دوباره فقط وقتی قبلی منقضی شده باشد (شرط `pending_payment` سفارش را ORD-04 بررسی می‌کند). درستی به job وابسته نیست: رزروی که `expires_at ≤ now` است در availability، reserve، commit و اصلاح دستی هیچ موجودی‌ای نگه نمی‌دارد و job فقط پاک‌سازی می‌کند. job زیر `pg_try_advisory_lock` (یک اجراکننده). audit برای هر چهار رخداد (created، committed، released، expired).
- تصمیم‌های کم‌اثر (خودم؛ بازبینی subagent):
  - رزرو در بازه نیمه‌باز `[created, expires_at)` معتبر است.
  - schema: `inventory_reservations` (`order_id` بدون FK تا ORD-01، `status`، `expires_at`، `committed_at`، `released_at`) با partial unique `(order_id) WHERE status IN ('active','committed')`. یعنی سفارشِ commit‌شده هم رزرو دوم نمی‌گیرد (409 `RESERVATION_ALREADY_CONSUMED`). `inventory_reservation_items` با وضعیت per-item (active، released، committed)، FK مرکب به variant و partial index روی آیتم‌های active.
  - ترتیب lock در همه مسیرها: advisory lock تراکنشی per-order (فقط reserve؛ اول از همه) → variantها `FOR SHARE` (محصول باید published و حذف‌نشده باشد) → inventory_items `FOR UPDATE` با `ORDER BY variant_id, warehouse_id` → ردیف‌های reservation `FOR UPDATE`. advisory lock دو فراخوانی یک سفارش را سریال می‌کند، پس تراکنش فراخواننده هیچ‌وقت با خطای unique مسموم نمی‌شود.
  - هر تغییر وضعیت یک آیتم رزرو زیر lock همان inventory_item انجام می‌شود. «آزادسازی تنبل»: نویسنده‌ها (reserve، اصلاح دستی INV-02 و بعداً commit) آیتم‌های رزروهای منقضی روی آیتم‌های قفل‌شده خود را released می‌کنند (movement `release` با reason `expired`، بدون audit؛ movement سند آن است). ردیف رزرو را commit، release یا job می‌بندند. خواننده‌ها (CAT-07، CAT-08، INV-07) موجودی آزاد را `total − reserved + Σ آیتم‌های active رزروهای منقضی` حساب می‌کنند (یک query گروهی؛ در لیست داخل SQL).
  - backstop در `inventory_movements`: یک `reserve` و یک `release`/`commit` برای هر `(inventory_item, reservation)` (partial unique).
  - reserve در تراکنش فراخواننده اجرا می‌شود و commit نمی‌کند. فقط از انبار پیش‌فرض؛ InventoryItem ناموجود = ناموجود (409) و ساخته نمی‌شود. lineها بر اساس variant ادغام می‌شوند؛ ورودی نامعتبر (خالی، غیر int، bool، بیش از سقف، جمع بیش از سقف) → 400؛ variant ناموجود، غیرفعال، غیرقابل‌خرید، بی‌قیمت یا محصول غیرمنتشر → 422؛ موجودی ناکافی → 409 `INSUFFICIENT_STOCK` با variant‌ها (all-or-nothing). همان سفارش با رزرو active معتبر: lineهای یکسان → همان رزرو (idempotent)، متفاوت → 409 `CONFLICT`.
  - invariant: `inventory_items.reserved_quantity == Σ quantity` آیتم‌های رزرو با وضعیت active؛ رزرو غیر active آیتم active ندارد. این جایگزین تعریف ADR-029 («رزرو منقضی تا آزادسازی موجودی را اشغال می‌کند») است.
  - CHECK `expires_at > created_at` گذاشته نشد چون `now` قابل تزریق است (تست مرز انقضا).
  - نمای admin (جزئیات محصول و تنوع) هم موجودی را با کسر نگه‌داشت‌های منقضی نشان می‌دهد، هم‌سو با صفحه عمومی و اصلاح دستی.
  - ریسک پذیرفته: reserve ردیف Product را قفل نمی‌کند؛ unpublish که همزمان commit شود جلوی reserve در حال اجرا را نمی‌گیرد (همان ADR-034).
  - INV-05 (commit/release؛ خودم، بازبینی subagent): هر دو در تراکنش فراخواننده، ترتیب lock: آیتم‌های رزرو (خواندن بدون lock) → inventory_items `FOR UPDATE` → ردیف رزرو `FOR UPDATE`؛ `now` بعد از گرفتن lock. commit: committed → `ALREADY_COMMITTED`؛ released/expired → `EXPIRED`؛ active ولی `expires_at ≤ now` یا با آیتمی که تنبل آزاد شده → آزادسازی باقی‌مانده، status expired، audit `reservation.expired` با actor=system و نتیجه `EXPIRED` (مقدار، نه exception؛ فراخواننده باید روی `outcome` شاخه بزند یا بعد از commit تراکنش `raise_for_expired()` → 409 `RESERVATION_EXPIRED`)؛ معتبر → `total` و `reserved` با هم کم می‌شوند، movement `commit`، audit `reservation.committed`. release: reason اجباری (1..500، وگرنه 400)؛ committed → 409 `RESERVATION_ALREADY_CONSUMED`؛ released/expired → no-op؛ active (حتی منقضی) → released با reason فراخواننده و `expired` در audit. رزرو ناموجود → 404. reserve وضعیت active و committed سفارش را در یک read می‌خواند و `_expire` روی رزرو committed → 409، تا رقابت re-reserve با commit به IntegrityError نرسد.
  - برای INV-06: job هر رزرو را در تراکنش جدا می‌بندد (lock آیتم‌ها، سپس ردیف رزرو)، تا هیچ‌وقت lock ردیف یک رزرو را هنگام lock آیتم‌های رزرو دیگر نگه ندارد.
  - INV-06 (خودم، بازبینی subagent): `sweep_expired_reservations` در `app/modules/inventory/jobs.py`. یک اجراکننده با `pg_try_advisory_xact_lock(73012, 1)` روی یک اتصال جدا که تا پایان sweep در تراکنش می‌ماند (lock با پایان تراکنش آزاد می‌شود و به pool نشت نمی‌کند؛ `idle_in_transaction_session_timeout = 0`). انتخاب بدون lock با keyset `(expires_at, id)` و سقف `max_batches`. هر رزرو در تراکنش جدا با `SET LOCAL lock_timeout` (پیش‌فرض 2s) → `ReservationService.expire`: آیتم‌ها `FOR UPDATE` و سپس ردیف رزرو `FOR UPDATE SKIP LOCKED`. رزرو ناموجود، غیر active، هنوز معتبر، قفل‌شده یا timeout → skipped (هرگز exception). خطای یک رزرو log و شمرده (`failed`) می‌شود. audit `reservation.expired` با actor=system، همان شکل commit منقضی. اجرا: loop در lifespan هر `RESERVATION_SWEEP_SECONDS` (پیش‌فرض 60، 0..3600، صفر = خاموش؛ تست‌ها صفر)، cancel قبل از dispose engine؛ دستی `python -m app.modules.inventory.jobs`.
- پیامدها: INV-04، INV-05، INV-06، INV-02 (اصلاح دستی)، CAT-07، CAT-08، INV-07، ORD-03، ORD-04 (موجودی آزاد مؤثر)، PAY-03، PAY-04.

### ADR-037 — Phase mode، دروازه فاز و تحویل image (تصمیم کاربر)
- تاریخ: 2026-10-12
- تصمیم: `/phase` batchها را تا COMPLETE شدن فاز زنجیره می‌کند (سقف جلسه ۴ batch؛ قواعد batch، AUTOPILOT، checklist و بازبین subagent ثابت). دروازه فاز: PR شاخه فاز به `master` → CI با staging موقت (image ساخته‌شده، دیتابیس خالی، `alembic upgrade head`، seed، smoke) → merge فقط توسط کاربر → CD: image در GHCR با tag `<sha>` و `phase-N` و git tag `phase-N` → شاخه فاز بعد از `master`.
- dependency بیرونی جدید: GitHub Container Registry. مجوز `packages:write` فقط در job مربوط به CD؛ بقیه jobها `contents: read`.
- staging موقت با `ENVIRONMENT` غیر production و OTP از mock SMS؛ هیچ secret واقعی ندارد.
- استقرار روی سرور staging یا production فقط در فاز ۵ (D13، OPS-04) با environment تأیید دستی.
- پیامدها: OPS-08، OPS-09، دروازه فاز ۲، `.claude/commands/phase.md`.

### ADR-038 — endpointهای ادمین موجودی (INV-08)
- تاریخ: 2026-10-12
- تصمیم‌های کم‌اثر (خودم؛ بازبینی subagent):
  - مجوز: `GET`ها با `inventory:read` یا `inventory:update` (PRD فقط `inventory:update` را نام می‌برد؛ `inventory:read` از seed AUTH-02 موجود بود و فقط admin و super_admin هر دو را دارند)؛ `PATCH` فقط `inventory:update`. اول authorization، بعد validation. همه پاسخ‌ها `no-store`.
  - `GET /admin/inventory`: یک ردیف برای هر تنوع حذف‌نشده از محصول حذف‌نشده (هر وضعیت انتشار). موجودی در SQL با همان قواعد `stock.py`: فقط انبار فعال (داخل subquery گروهی که LEFT JOIN می‌شود)، reserved هر آیتم `GREATEST(0, reserved − نگه‌داشت منقضی)`، threshold جمع می‌شود، تنوع بدون آیتم → صفر و `out_of_stock`. فیلترها `q` (SKU یا عنوان؛ wildcardها escape)، `product_id`، `stock_status`؛ sort `sku` (پیش‌فرض)، `free_asc`، `free_desc`، `updated` (NULLS LAST)؛ tie-break `variant_id`.
  - `PATCH /admin/inventory/{variant_id}`: بدنه `adjustment_type` + `quantity` (با هم)، `low_stock_threshold`، `reason` (همیشه اجباری)، `expected_total` اختیاری. همه int strict در `0..MAX` (bool، float، رشته → 400). فیلدهای سیستمی ردیف لیست (`total`، `reserved`، `free`، `stock_status`، …) حذف و نادیده گرفته می‌شوند. `expected_total` محافظ ارسال دوباره است (افزوده نسبت به PRD): نابرابر با total زیر lock → 409 `CONFLICT` با `details.type = stale_total`، بدون movement و audit. threshold فقط audit `inventory.threshold_updated` دارد (شمارنده نیست، movement ندارد). همه در یک تراکنش با ترتیب lock ADR-034؛ پاسخ زیر همان lock خوانده می‌شود. threshold روی تنوع بی‌آیتم آیتم با total صفر می‌سازد (حتی وقتی چیزی تغییر نکند، مثل correction no-op در ADR-034). `expected_total` با total انبار پیش‌فرض مقایسه می‌شود که در v1 همان total ردیف است؛ چندانباره باید آن را بازبینی کند. بدنه JSON خراب بدون token → 400 (FastAPI بدنه را قبل از dependencyها parse می‌کند؛ مثل بقیه PATCHهای ادمین).
  - `GET /admin/inventory/reservations`: فیلتر `status`، `order_id`، `variant_id` (EXISTS). وضعیت نمایشی مستقل از job: active با `expires_at ≤ now` → `expired`؛ آیتم active همان رزرو هم `expired` نمایش داده می‌شود. آیتم‌ها با یک query دوم (بدون N+1).
  - `GET /admin/inventory/{variant_id}/history`: movementهای همه انبارها، `created_at desc, id desc`. variant حذف‌شده دیده می‌شود (مثل ADR-030)؛ تنوع بی‌آیتم → 200 خالی؛ ناموجود → 404. ریسک پذیرفته: دو movement یک تراکنش (آزادسازی تنبل و سپس اصلاح) ممکن است `created_at` برابر داشته باشند و ترتیب نسبی‌شان با `id` تصادفی است؛ ستون `seq` به migration نیاز دارد و به بعد موکول شد.
- پیامدها: INV-08، INV-09، ADM-* (پنل).

### ADR-039 — نیازمندی‌های جریان خرید فاز ۳ (D30–D34؛ تصمیم کاربر)
- تاریخ: 2026-10-12
- تصمیم (کاربر تأیید کرد؛ CART-00، DSC-00، ADDR-00، ORD-00، PAY-00):
  - D30: cart token مهمان در cookie `cart_token` با `HttpOnly; Secure; SameSite=Lax; Path=/api/v1`؛ فقط hash ذخیره می‌شود. بعد از ادغام در `verify-otp` cookie پاک می‌شود.
  - D31: `POST /orders` یک redemption `pending` می‌سازد که در سقف کل و سقف هر کاربر (موبایل نرمال‌شده) شمرده می‌شود؛ پرداخت موفق → `confirmed`؛ فقط لغو سفارش یا انقضای رزرو → `released` (شکست پرداخت نگهش می‌دارد). قبل از شمارش، ردیف DiscountCode با `FOR UPDATE` قفل می‌شود؛ تست همزمانی روی آخرین استفاده.
  - D32: پرداخت موفق بعد از انقضای رزرو: رزرو منقضی مصرف نمی‌شود؛ payment `refund_required`، سفارش `cancelled` (reason `expired`)، بازپرداخت دستی؛ audit `payment.refund_required` با actor system در همان تراکنش و log WARNING (شماره سفارش، id پرداخت، مبلغ؛ بدون PII). ادمین سفارش‌ها و پرداخت‌ها را با `refund_required` فیلتر می‌کند (فاز ۴).
  - D33: کد تخفیف روی کل سبد (محدودیت دسته یا محصول بعداً)؛ ارسال = هزینه ثابت روش + سقف ارسال رایگان اختیاری (منطقه‌ای بعداً)؛ `POST /orders/{id}/recalculate` موکول شد و سفارش تغییرناپذیر است.
  - D34: (۱) شکست پرداخت رزرو و redemption را نگه می‌دارد و تلاش دوباره تا پایان مهلت رزرو ممکن است؛ فقط لغو یا انقضا آزادشان می‌کند. (۲) job انقضای رزرو سفارش را `cancelled` با reason `expired` می‌کند و redemption را آزاد می‌کند؛ audit با actor system. (۳) `POST /cart/discount` rate limit دارد (تلاش ناموفق به‌ازای کاربر یا سبد و به‌ازای IP؛ بعد از سقف 429). (۴) بعد از پرداخت موفق فقط تعداد تنوع‌های سفارش از سبد کم می‌شود؛ ثبت سفارش سبد را خالی نمی‌کند. (۵) `Idempotency-Key`: محدوده هر کاربر، مهلت ۲۴ ساعت؛ همان کلید و همان بدنه → پاسخ اولیه؛ بدنه متفاوت → 422. (۶) مبنای سقف ارسال رایگان: جمع بعد از همه تخفیف‌ها و قبل از مالیات؛ fingerprint quote کد تخفیف و ارسال را هم پوشش می‌دهد.
- تصمیم‌های کم‌اثر (خودم): سقف ۵۰ خط سبد، انقضای ۳۰ روزه سبد مهمان، حداکثر ۱۰ آدرس، کد پستی ۱۰ رقمی، شماره سفارش `ORD-YYYY-NNNNNN`، سقف‌های rate limit کد در `Settings` (پیش‌فرض پیشنهادی: ۱۰ تلاش ناموفق در ۱۵ دقیقه برای هر کاربر یا سبد، ۳۰ برای هر IP؛ در DSC-03 نهایی می‌شود).
- پیامدها: CART-01..05، DSC-01..05، ADDR-01..04، ORD-01..06، PAY-01..06، INV-06 (لغو سفارش در انقضا از طریق ORD/PAY)، ADM (فیلتر `refund_required`).

### ADR-040 — سبد خرید: schema و API (CART-01، CART-02)
- تاریخ: 2026-10-12
- تصمیم‌های کم‌اثر (خودم؛ بازبینی subagent برای CART-02):
  - `carts`: دقیقاً یکی از `user_id` و `token_hash` (CHECK)؛ `expires_at` فقط برای سبد مهمان، لغزنده: هر نوشتن موفق آن را `now + 30 روز` می‌کند و cookie دوباره set می‌شود؛ status `active`، `merged`، `expired`؛ یک سبد active برای هر کاربر (partial unique)؛ `user_id` با CASCADE (سبد داده شخصی است). `cart_items`: FK مرکب variant+product با RESTRICT (variant فقط حذف نرم می‌شود)، qty `1..MAX_STOCK_QUANTITY`، یک خط برای هر variant.
  - cookie `cart_token` فقط وقتی شکل token ما را دارد خوانده می‌شود؛ مقدار دیگر نادیده گرفته می‌شود (سبد جدید). با Bearer معتبر، سبد کاربر استفاده می‌شود و cookie نادیده گرفته می‌شود (ادغام در CART-04).
  - هر نوشتن روی سبد زیر `FOR UPDATE` ردیف cart؛ موجودی فقط خوانده می‌شود (رزرو نمی‌کند). موجودی آزاد مؤثر = همان قاعده CAT-07/INV-07 (انبار فعال، کسر نگه‌داشت منقضی).
  - خطاها: variant ناموجود، حذف‌شده، غیرفعال، بی‌قیمت یا محصول غیرمنتشر/حذف‌شده → 404 (مثل read عمومی)؛ `is_purchasable = false` → 422؛ تعداد بیش از موجودی آزاد → 409 `INSUFFICIENT_STOCK`؛ خط پنجاه‌ویکم → 422؛ خط سبد دیگری → 404. افزودن variant موجود در سبد تعداد را جمع می‌کند.
  - این نگاشت عمداً با reserve (ADR-036، همه 422) فرق دارد: سبد مثل read عمومی رفتار می‌کند؛ ORD-03/ORD-04 از ADR-036 پیروی می‌کنند.
  - `POST` با variant موجود همان خط را جمع می‌کند و 201 می‌دهد. سقف ۵۰ خط بعد از lock سبد شمرده می‌شود و فقط برای خط جدید اعمال می‌شود. 409 هیچ عددی از موجودی ندارد (نه در details، نه در message).
  - `PATCH`: کاهش همیشه مجاز است (بدون بررسی موجودی یا وضعیت variant)؛ افزایش variant قابل‌فروش و موجودی کافی می‌خواهد؛ خطی که variantش دیگر عمومی نیست هنگام افزایش 422 با `details.type = variant_unavailable` می‌گیرد. `DELETE` همیشه کار می‌کند.
  - هویت: هر header `Authorization` (حتی غیر Bearer یا خالی) باید معتبر باشد وگرنه 401؛ هرگز به مهمان برنمی‌گردد. کاربر مسدود 403. Bearer معتبر + cookie: سبد کاربر، بدون Set-Cookie. PATCH/DELETE مهمان یا کاربر بدون سبد → 404 بدون ساخت سبد. cookie سبد بسته یا منقضی → سبد و token جدید (هرگز hash قدیمی دوباره درج نمی‌شود).
  - CSRF: درخواست cross-site با content type ساده (فرم) به endpoint نمی‌رسد (400، بدون سبد و cookie)؛ JSON cross-site را CORS با allowlist می‌بندد.
  - ترتیب lock ادغام (CART-04): سبد کاربر → سبد مهمان. race پذیرفته: دو POST همزمان مهمان بدون cookie دو سبد می‌سازند و یکی تا انقضا یتیم می‌ماند.
  - ادغام (CART-04): بعد از commit ورود، در تراکنش جدا (شکست ادغام ورود را خراب نمی‌کند؛ log `cart.merge_failed` و cookie برای ورود بعدی می‌ماند). lock: سبد کاربر (ساخته می‌شود) → سبد مهمان. خطوط مهمان به ترتیب id: variant غیرقابل‌فروش یا بی‌موجودی → حذف؛ variant موجود در سبد کاربر → جمع تا سقف موجودی آزاد و هرگز کمتر از مقدار فعلی کاربر (مبنای قیمت فقط اگر تعداد تغییر کند rebase می‌شود)؛ خط جدید → `min(qty, free)` با مبنای قیمتی که مهمان دیده بود؛ سقف ۵۰ خط → حذف خط جدید. سبد مهمان `merged` می‌شود (idempotent؛ ادغام همزمان یک‌بار اثر دارد). cookie نامعتبر، ناشناخته یا منقضی → ورود موفق و cookie پاک؛ بدون cookie → بدون Set-Cookie سبد.
  - `ON CONFLICT` روی partial unique با predicate متنی (نه پارامتر): asyncpg بعد از پنج اجرا به generic plan می‌رود و predicate پارامتری دیگر با index تطبیق نمی‌خورد (تست regression).
- پیامدها: CART-02..05، ORD-03، ORD-04.

### ADR-041 — نمای سبد و flag تغییر قیمت (CART-03)
- تاریخ: 2026-10-12
- تصمیم (کاربر): مبنای per-line روی `cart_items` (`seen_unit_price`، `seen_price_version`)؛ هر نوشتن روی یک خط مبنای همان خط را به‌روز می‌کند و `POST /cart/acknowledge-prices` همه خطوط را؛ `GET /cart` قیمت قبلی و جدید هر خط تغییرکرده را نشان می‌دهد؛ flag فقط UX است و امنیت سفارش با fingerprint و 409 `PRICE_CHANGED` در ORD-03/ORD-04 است.
- تصمیم‌های کم‌اثر (خودم؛ بازبینی subagent):
  - `price_changed` = قیمت نهایی واحد فعلی ≠ `seen_unit_price`. نسخه قیمت در مقایسه نیست: شروع یا پایان بازه sale نسخه را عوض نمی‌کند و تغییر نسخه بدون تغییر قیمت نهایی تغییر نیست. `seen_price_version` فقط برای عیب‌یابی و استفاده بعدی ذخیره می‌شود. وقتی قیمت به مقدار دیده‌شده برگردد flag خودش پاک می‌شود. `previous_unit_price` = مبنا وقتی تغییر کرده، وگرنه null.
  - مبنا فقط وقتی قیمت فعلی وجود دارد به‌روز می‌شود؛ خطی که variantش قیمت ندارد مبنای قبلی را نگه می‌دارد (کاهش تعداد و acknowledge).
  - خط «قابل‌دسترس» = همان predicate افزودن به سبد (`is_sellable`: variant فعال، حذف‌نشده، قیمت‌دار، قابل‌خرید؛ محصول منتشرشده و حذف‌نشده). خط غیرقابل‌دسترس قیمت‌گذاری نمی‌شود (مبالغ null، `stock_status` null). خط با موجودی ناکافی یا ناموجود قیمت‌گذاری می‌شود و `stock_status` آن `insufficient` یا `out_of_stock` است؛ ثبت سفارش ردش می‌کند. هیچ عدد موجودی در پاسخ نیست؛ `insufficient` امکان جست‌وجوی دودویی موجودی را می‌دهد که معادل 409 همان CART-02 است (پذیرفته).
  - تنظیمات قیمت: سبد خالی یا بدون خط قابل‌دسترس بدون خواندن ردیف تنظیمات صفر برمی‌گرداند؛ نبود ردیف برای سبد قیمت‌دار پیکربندی غلط است → 500 با شکل خطای استاندارد و log ERROR (بدون policy پیش‌فرض).
  - خطوط به ترتیب id خط به `price_order` داده می‌شوند (`price_cart_lines`؛ ADR-031). `shipping_amount` در سبد همیشه 0 است (انتخاب در checkout).
  - `GET /cart` بدون lock و بدون Set-Cookie؛ بدون سبد → سبد خالی 200 و سبدی ساخته نمی‌شود. `acknowledge-prices` همان شکل پاسخ GET را برمی‌گرداند؛ بدون سبد → سبد خالی بدون cookie؛ بدنه ندارد، پس در برابر فرم cross-site به SameSite=Lax (cookie مهمان فرستاده نمی‌شود) و Bearer (header فرستاده نمی‌شود) تکیه دارد (تست).
  - flag فقط روی خط قابل‌خرید نشان داده می‌شود؛ خط غیرقابل‌دسترس `price_changed = false`. خط غیرقابل‌دسترس عنوان، slug و SKU محصول را حتی اگر حذف نرم یا غیرمنتشر شده باشد نشان می‌دهد: سبد خود کاربر است و باید بداند کدام خط را حذف کند (استثنای آگاهانه از SD rule برای read عمومی).
  - `acknowledge-prices` و نمای بعدی دو تراکنش‌اند؛ تغییر قیمت بین آن دو ممکن است در پاسخ flag بگیرد (برای flag UX پذیرفته است).
  - migration `20261012_0018`: backfill با قیمت نهایی فعلی در یک UPDATE با `now()` و بازه نیمه‌باز؛ variant بی‌قیمت → 0 (فقط برای variant غیرعمومی ممکن است و در مقایسه شرکت نمی‌کند).
- پیامدها: CART-03، CART-04، ORD-03.

### ADR-042 — schema کد تخفیف و redemption (DSC-01)
- تاریخ: 2026-10-18
- تصمیم‌های کم‌اثر (خودم؛ بازبینی opus):
  - `discount_codes`: `code` نرمال‌شده (trim، upper، فقط ASCII `[A-Z0-9_-]{3,32}`؛ ورودی غیر ASCII حتی رقم فارسی رد می‌شود تا `upper()` دو ورودی متفاوت را یکی نکند)؛ unique بین کدهای حذف‌نشده (soft delete؛ کد استفاده‌شده با FK RESTRICT پاک نمی‌شود). `type` + `value`: percent به basis point (`1..10000`، هم‌واحد calculator)، fixed به تومان. `max_amount` فقط برای percent. `min_order_amount` در `1..MAX` (NULL = بدون حداقل). بازه `[starts_at, ends_at)` با پایان باز. `usage_limit_per_user ≤ usage_limit_total`. `is_active` پیش‌فرض true.
  - `discount_redemptions`: `order_id` NOT NULL بدون FK تا ORD-01 (همان‌جا FK رزرو و redemption اضافه می‌شود). یک redemption زنده (`pending`/`confirmed`) برای هر سفارش (partial unique). وضعیت: `released_at` ⟺ released؛ confirmed ⟹ `confirmed_at`؛ pending ⟹ بدون `confirmed_at`؛ released بعد از confirmed مجاز است و `confirmed_at` می‌ماند (لغو یا بازپرداخت بعد از پرداخت، D32). `amount` در `0..MAX` (درصد کوچک ممکن است صفر گرد شود و کد همچنان اعمال‌شده است). `phone` (E.164) کلید سقف هر کاربر و `code` snapshot متن کد هنگام سفارش؛ تغییر بعدی کد روی سفارش‌های قبلی اثر ندارد. indexهای شمارش partial روی وضعیت زنده.
  - `carts.discount_code_id` (nullable، SET NULL، بدون index: کدها فقط حذف نرم می‌شوند و scan روی carts فقط در حذف سخت پیش می‌آید) در همین migration برای DSC-03. index شمارش: فقط `(discount_code_id, phone)` partial؛ برای شمارش کل هم کافی است. جدول تلاش‌های ناموفق rate limit کد (D34) در DSC-03 ساخته می‌شود.
  - برای DSC-03/04 و ORD-04: هر `ON CONFLICT` روی partial unique با predicate متنی (ADR-040). حذف نرم و غیرفعال‌کردن کد (DSC-04) همان `FOR UPDATE` ردیف DiscountCode را می‌گیرد که ORD-04 می‌گیرد، و ORD-04 بعد از lock دوباره `deleted_at IS NULL AND is_active` را بررسی می‌کند.
- پیامدها: DSC-02..05، ORD-01، ORD-04، PAY-03، PAY-04.

### ADR-043 — قواعد کد تخفیف و اعمال آن روی سبد (DSC-02، DSC-03)
- تاریخ: 2026-10-18
- تصمیم‌های کم‌اثر (خودم؛ بازبینی opus):
  - قواعد خالص (`app/modules/discounts/rules.py`) فقط تصمیم می‌گیرند؛ مبلغ فقط از `price_order` (ADR-031). ترتیب قطعی rejection: `invalid` (ناموجود، حذف‌شده، غیرفعال یا هنوز شروع‌نشده؛ یکسان تا وجود کد آینده یا غیرفعال لو نرود) → `expired` (بازه نیمه‌باز) → `exhausted` → `user_exhausted` → `below_minimum`؛ بعد از قیمت‌گذاری `no_eligible_lines`. `expired`، `exhausted` و `below_minimum` وجود کد را نشان می‌دهند؛ برای UX پذیرفته است و دفاع، rate limit است. پاسخ 422 `DISCOUNT_NOT_APPLICABLE` با `details.type` و بدون عدد.
  - مبنای حداقل سفارش: خطوط قیمت‌گذاری‌شده (قابل‌خرید، حتی کم‌موجود) بعد از تخفیف محصول و قبل از کد، مالیات و ارسال (`subtotal − product_discount_total` بدون کد). با مبنای ارسال رایگان (D34، بعد از همه تخفیف‌ها) فرق دارد. ORD-04 با خطوط سفارش دوباره بررسی می‌کند.
  - سقف هر کاربر با موبایل نرمال‌شده؛ مهمان (`user_live=None`) در سبد بررسی نمی‌شود و ORD-04 با موبایل تأییدشده بررسی می‌کند. شمارش کل و هر کاربر در یک query با `FILTER` روی redemptionهای زنده.
  - `POST /cart/discount`: lock سبد (بدون سبد → 404) → advisory lock روی IP → شمارش تلاش‌های ناموفق در پنجره برای owner (کاربر: `user_id`؛ مهمان: `cart_id`)، IP و سراسری؛ رسیدن به هر سقف → 429 `RATE_LIMITED` با `Retry-After` از قدیمی‌ترین تلاش و `details.type = too_many_attempts_<scope>`؛ سقف سراسری (پیش‌فرض ۱۰٬۰۰۰، چون رسیدن به آن همه را مسدود می‌کند) log WARNING دارد (overshoot محدود پذیرفته). `Retry-After` از تلاشی حساب می‌شود که خروجش از پنجره اولین جای خالی را باز می‌کند ((count − cap + 1)-امین قدیمی‌ترین). سپس نرمال‌سازی (شکل بد → `invalid`، شمرده می‌شود؛ پس شکل بد 422 است نه 400؛ فقط فیلد اضافه، خالی یا بیش از ۶۴ کاراکتر 400). شکست: ردیف تلاش در همان تراکنش درج و commit و سپس 422؛ ردیف‌های قدیمی‌تر از پنجره همان‌جا در دسته‌های حداکثر ۵۰۰ تایی با `SKIP LOCKED` پاک می‌شوند (بدون انتظار یا deadlock بین شکست‌های همزمان). موفقیت شمارنده را صفر نمی‌کند، کد قبلی را جایگزین می‌کند، سبد را touch و cookie مهمان را تمدید می‌کند و مبنای قیمت خطوط را عوض نمی‌کند. شکست، کد قبلی سبد را نگه می‌دارد. اعمال دوباره همان کد 200.
  - بودجه مهمان با پاک‌کردن cookie (سبد جدید) یا ورود (شمارش به `user_id` می‌رود) تازه می‌شود؛ پس سقف IP مهم‌ترین حد است. `client_ip` پشت reverse proxy همه را یک IP می‌بیند: پیکربندی trusted-proxy در OPS-04 (D13) پیش‌شرط انتشار production است (بدون آن سقف IP و سراسری عملاً برای همه مشترک‌اند)؛ تا آن زمان سقف IP قابل تنظیم است (`DISCOUNT_MAX_FAILED_PER_IP`).
  - `DELETE /cart/discount`: idempotent؛ بدون سبد → سبد خالی 200. هر دو پاسخ `CartResponse` با `no-store`.
  - خواندن (`GET /cart`، `acknowledge-prices`) کد را دوباره بررسی می‌کند و هرگز پاکش نمی‌کند؛ پاسخ `discount: {code, applied, reason}`؛ کد اعمال‌نشده `has_changes` را true می‌کند. `applied: true` تضمین نیست: شمارش قطعی با `FOR UPDATE` در ORD-04 است (D31). ردیف کد در سبد قفل نمی‌شود.
  - ادغام ورود: کد سبد مهمان فقط وقتی سبد کاربر کد ندارد منتقل می‌شود.
- پیامدها: DSC-02، DSC-03، DSC-05، ORD-03، ORD-04، OPS-04.

### ADR-044 — مدیریت کد تخفیف و redemption سفارش (DSC-04، DSC-05)
- تاریخ: 2026-10-18
- تصمیم‌های کم‌اثر (خودم؛ بازبینی opus):
  - ادمین (`/admin/discounts`، مجوز `discounts:manage`): درصد در API هم basis point است (هم‌واحد DB و calculator). قواعد شکل بدنه 400؛ در PATCH فقط تعارض با مقدار ذخیره‌شده 422 (بازه، per_user ≤ total، max_amount روی fixed، درصد بیش از ۱۰۰٪ برای کد درصدی). `code` و `type` بعد از ساخت تغییر نمی‌کنند (برابر مقدار فعلی no-op، متفاوت 400). کاهش سقف زیر شمارش فعلی مجاز است و فقط استفاده‌های بعدی را می‌بندد. کد تکراری بین کدهای زنده 409 (پیش‌بررسی و IntegrityError با نام index)؛ ساخت دوباره متن یک کد حذف‌شده با id جدید و شمارش صفر. حذف نرم؛ DELETE دوم 404. هر نوشتن زیر `FOR UPDATE` ردیف کد؛ audit `discount.created/updated/deleted` (فقط فیلدهای تغییرکرده؛ no-op بدون audit). لیست: `q` با escape، `state` (`active`، `scheduled`، `expired`، `inactive`، با یک `now`)، sort `newest`/`code`، شمارش pending/confirmed/released در یک query گروهی.
  - تغییر یا حذف کد به redemptionهای قبلی دست نمی‌زند؛ سفارش pending همچنان confirm می‌شود.
  - `RedemptionService` (داخلی، در تراکنش فراخواننده): ترتیب سراسری lock در جریان خرید: idempotency (ADR-046) → سبد → advisory سفارش → variant/inventory → ردیف کد → redemption. `redeem` ردیف کد را قفل می‌کند و فقط زیر آن می‌شمارد؛ قواعدی را می‌گیرد که سفارش با آن قیمت‌گذاری شده (`priced_rules`) و اگر قواعد قفل‌شده فرق کنند 409 `PRICE_CHANGED` (ORD-04 می‌تواند با `lock_code` اول قفل و سپس قیمت‌گذاری کند). هر سفارش حداکثر یک redemption: retry با همان کد، مبلغ و موبایل همان را برمی‌گرداند، هر حالت دیگر (حتی redemption آزادشده) 409. ورودی‌ها: amount و subtotal int در `0..MAX`، amount ≤ subtotal، موبایل E.164؛ ORD-04 وقتی `code_applied=false` است redeem نمی‌کند.
  - `confirm`/`release` فقط ردیف redemption را قفل می‌کنند (release فقط شمارش را کم می‌کند؛ بدون چرخه با job انقضا که inventory را اول قفل می‌کند) و هرگز raise نمی‌کنند: outcome (`CONFIRMED`، `ALREADY_CONFIRMED`، `RELEASED`، `NONE` / `RELEASED`، `ALREADY_RELEASED`، `NONE`). PAY-03 وقتی commit رزرو `EXPIRED` است `release` صدا می‌زند نه `confirm` (D32). بازپرداخت redemption تأییدشده را released می‌کند و `confirmed_at` می‌ماند؛ `released_at ≥ confirmed_at`.
- پیامدها: DSC-04، DSC-05، ORD-04، PAY-03، PAY-04، INV-06 (لغو در انقضا).

### ADR-045 — آدرس مشتری و روش ارسال (ADDR-01، ADDR-02)
- تاریخ: 2026-10-18
- تصمیم‌های کم‌اثر (خودم؛ بازبینی opus برای ADDR-02):
  - آدرس: فقط کاربر واردشده و فقط آدرس‌های خودش (آدرس دیگران 404). حداکثر ۱۰ آدرس (بیشتر → 422). اولین آدرس پیش‌فرض می‌شود؛ پیش‌فرض جدید قبلی را برمی‌دارد؛ PATCH می‌تواند پیش‌فرض را بردارد (بدون پیش‌فرض مجاز است). حذف سخت (سفارش snapshot دارد)؛ حذف پیش‌فرض، جدیدترین آدرس باقی‌مانده را پیش‌فرض می‌کند. هر نوشتن زیر advisory lock هر کاربر (سقف و یک پیش‌فرض در همزمانی؛ partial unique پشتیبان DB). موبایل گیرنده با `normalize_phone` به E.164؛ کد پستی ۱۰ رقم (رقم فارسی/عربی، فاصله و خط تیره پذیرفته و حذف می‌شوند). بدون audit (تغییر حساس طبق CLAUDE.md نیست) و بدون PII در log.
  - روش ارسال: فقط حذف نرم؛ FK آینده Shipment به آن RESTRICT و سفارش snapshot شناسه، عنوان و مبلغ ارسال را نگه می‌دارد. `cost` در `0..MAX` (صفر = همیشه رایگان؛ صفر با سقف مجاز و بی‌اثر)، `free_shipping_threshold` در `1..MAX`، `description` اختیاری (خارج از مدل PRD، برای نمایش). فهرست عمومی فقط فعال و حذف‌نشده به ترتیب `display_order`، عنوان، id، با فیلدهای `id`، `title`، `description`، `cost`، `free_shipping_threshold`.
  - محاسبه‌گر پشت `ShippingCalculator` (v1: `FlatRateCalculator`): رایگان وقتی `basis ≥ threshold` («برسد»). `ShippingContext` استان و شهر را برای قیمت منطقه‌ای بعدی (D33) دارد. مبنا (D34): `shipping_basis = subtotal − product_discount_total − discount_code_amount` (بعد از همه تخفیف‌ها، قبل از مالیات، بدون ارسال)؛ با مبنای حداقل کد (ADR-043، قبل از کد) فرق دارد. کد اعمال‌نشده در مبنا نیست.
  - ترتیب برای ORD-03/ORD-04 (بدون دور: کد و مالیات هرگز ارسال را نمی‌خوانند): قیمت‌گذاری با `shipping=0` (و کد اگر `price_with_code` پذیرفت) → مبنا → quote → `price_order(shipping=quote)`؛ خطوط، مالیات و کد یکسان و `grand_total` دقیقاً به اندازه quote بیشتر. ارسال گرد نمی‌شود و مالیات ندارد (ADR-031). fingerprint quote در ORD-03 باید علاوه بر fingerprint قیمت، شناسه و مبلغ کد و شناسه و مبلغ ارسال را بپوشاند (D34).
  - طول عنوان و توضیح را نوع ستون (VARCHAR 100/500) تضمین می‌کند؛ CHECK فقط trim و ناتهی‌بودن عنوان. `get_selectable` قفل نمی‌گیرد: روشی که وسط checkout غیرفعال شود همچنان در آن سفارش استفاده می‌شود و سفارش snapshot آن را نگه می‌دارد (پذیرفته؛ ORD-04).
  - انتخاب روش در checkout: `ShippingRepository.get_selectable` — روش ناموجود، حذف‌شده یا غیرفعال همه یک پاسخ 422 با `details.type = shipping_method_unavailable`.
  - ادمین روش ارسال (ADDR-03): مجوز جدید `shipping:manage` (admin و super_admin؛ نه support و content_manager)، فقط از seed و بدون migration. عنوان یکتا نیست (بدون 409). فهرست ادمین ترتیب ثابت `display_order`، عنوان، id و فیلتر `q`/`state`، بدون sort. audit: ایجاد snapshot کامل، ویرایش فقط فیلدهای تغییرکرده، حذف snapshot کامل قبل.
- پیامدها: ADDR-01..04، ORD-01، ORD-03، ORD-04.

### ADR-046 — schema سفارش و Idempotency-Key (ORD-01، ORD-02)
- تاریخ: 2026-10-18
- تصمیم‌های کم‌اثر (خودم؛ بازبینی opus):
  - جدول‌ها: `orders` (سه وضعیت مستقل، `cancel_reason` اجباری فقط برای cancelled، اجزای مبلغ BIGINT با CHECK جمع در numeric، موبایل، کد و روش ارسال snapshot)، `order_items` (snapshot عنوان محصول، SKU، برچسب تنوع، قیمت واحد اصلی و نهایی و اجزای خط طبق نگاشت ADR-031؛ `position` = ترتیب پایدار قیمت‌گذاری)، `order_price_snapshots` (سیاست قیمت، fingerprint quote در ORD-03، هزینه روش قبل از سقف رایگان و سقف)، `order_addresses` (کپی بدون FK)، `order_status_history`. همه FKهای به سفارش، محصول، کد و روش ارسال RESTRICT؛ `inventory_reservations.order_id` و `discount_redemptions.order_id` اکنون FK به orders دارند. migration ردیف یتیم را حذف نمی‌کند و متوقف می‌شود.
  - جمع سرآیند = Σ خطوط با CHECK ممکن نیست؛ ORD-04 در service assert و تست می‌کند.
  - شماره سفارش: `ORD-<سال میلادی UTC>-<sequence سراسری، حداقل ۶ رقم>`؛ sequence سالانه reset نمی‌شود و gap مجاز است. CHECK سال شماره = سال UTC `created_at`؛ ORD-04 هر دو را از یک `now` می‌سازد.
  - Shipment جدا (کد رهگیری) به ADM فاز ۴ موکول شد؛ تا آن موقع وضعیت ارسال، روش و هزینه روی `orders` است.
  - حذف حساب کاربر (فاز ۴) با `orders.user_id RESTRICT` به ناشناس‌سازی کاربر نیاز دارد، نه حذف.
  - Idempotency-Key (ORD-02): جدول `idempotency_keys` (کاربر، scope، key؛ CASCADE با حذف کاربر). `IdempotencyService` در تراکنش فراخواننده و اول از همه lockها: `pg_advisory_xact_lock(hashtextextended('idem:<scope>:<user>:<key>', 0))`؛ برخورد hash فقط انتظار اضافه است. hash = sha256 روی JSON canonical از پارامترهای مسیر و بدنه parse‌شده (`mode="json"`). همان hash → replay وضعیت و بدنه ذخیره‌شده (فقط این دو؛ هدرهای دیگر مثل `Location` replay نمی‌شوند؛ ترتیب کلیدهای JSONB ممکن است فرق کند) با `Cache-Control: no-store`؛ hash متفاوت → 422 `IDEMPOTENCY_KEY_REUSED`؛ منقضی (`expires_at ≤ now`، ۲۴ ساعت) → حذف و اجرای تازه. فقط پاسخ 2xx ذخیره می‌شود تا retry بعد از خطا ممکن باشد. header نبود/نامعتبر (۱..۲۵۵ ASCII قابل چاپ بدون فاصله) → 400، بعد از احراز هویت. `purge_expired_idempotency_keys` هنوز به job وصل نیست (بدنه‌های ذخیره‌شده تا purge می‌مانند)؛ در OPS/INV-06 وصل شود.
- پیامدها: ORD-02..06، PAY-*، ACC-01، ADM-01، CAT-17.

### ADR-047 — checkout validate، state machine سفارش و فروش موفق (ORD-03، ORD-05، CAT-17)
- تاریخ: 2026-10-18
- تصمیم‌های کم‌اثر (خودم؛ بازبینی opus):
  - `POST /checkout/validate`: فقط کاربر واردشده؛ سبد خالی 422 (`cart_empty`)؛ آدرس دیگران یا ناموجود 404 (قاعده مالکیت)؛ روش ارسال غیرقابل‌انتخاب 422؛ خط غیرقابل‌فروش 422 (`line_unavailable`، SD rule)؛ موجودی آزاد مؤثر ناکافی 409 `INSUFFICIENT_STOCK`؛ کد اعمال‌شده‌ای که دیگر اعمال نمی‌شود 422 `DISCOUNT_NOT_APPLICABLE` با reason (quote بدون کد برگردانده نمی‌شود؛ کاربر باید کد را بردارد). fingerprint quote = sha256 روی fingerprint calculator + تعداد هر خط + `grand_total` + کد (id، مبلغ، type، value، max_amount) + روش (id، هزینه، سقف، مبلغ ارسال). `build_quote` بدون تراکنش و lock، با کد از پیش قفل‌شده اختیاری و امکان رد بررسی موجودی (ORD-04 بعد از reserve).
  - state machine: order `pending_payment → confirmed | cancelled`، `confirmed → completed`؛ payment `unpaid → pending`، `pending → paid | failed | refund_required`، `failed → pending | paid | refund_required`؛ shipment `not_shipped → preparing → shipped → delivered`. guardها: order→confirmed فقط با paid؛ order→completed فقط با delivered؛ order→cancelled فقط اگر paid نیست؛ payment→pending/paid فقط با order pending_payment؛ payment→refund_required فقط با order cancelled (PAY-03 اول سفارش را لغو می‌کند)؛ shipment→preparing فقط با order confirmed. همان وضعیت 422. هر انتقال: ردیف history و audit `order.status_changed` در همان تراکنش.
  - ترتیب سراسری lock (ادامه ADR-044/046): idempotency → سبد → advisory سفارش → **ردیف سفارش** → inventory → کد → redemption. job انقضای رزرو (ADR-036) وقتی سفارش را لغو می‌کند باید اول ردیف سفارش را با `FOR UPDATE SKIP LOCKED` (و `lock_timeout`) قفل کند و بعد `expire`؛ تغییر `app/modules/inventory/jobs.py` در ORD-06.
  - «فروش موفق» (CAT-17 و گزارش‌ها): `orders.payment_status = 'paid'` (یک helper)؛ سفارش لغو یا refund_required شمرده نمی‌شود.
- پیامدها: ORD-04، ORD-06، PAY-02..04، INV-06، CAT-17، ADM.

### ADR-048 — ثبت سفارش و ترتیب سراسری lock (ORD-04؛ تأیید کاربر با ۴ افزوده)
- تاریخ: 2026-10-18
- تصمیم (کاربر plan را تأیید کرد): (۱) حداکثر یک سفارش `pending_payment` برای هر کاربر: `POST /orders` دوم → 409 `ORDER_PENDING` با شماره سفارش موجود. (۲) همه مسیرها از ترتیب سراسری lock پیروی می‌کنند و برای هر مسیر موجود تست همزمانی هست. (۳) شماره سفارش فقط از sequence (gap مجاز، هرگز `MAX()+1`). (۴) تلاش ناموفق (4xx) کلید idempotency را ذخیره نمی‌کند و همان کلید دوباره قابل استفاده است.
- ترتیب سراسری lock (جایگزین ADR-044/046/047): idempotency (advisory) → سبد (`FOR UPDATE`) → **ردیف کد** (`FOR UPDATE`) → advisory سفارش → ردیف سفارش → variantها (`FOR SHARE`) / inventory (`FOR UPDATE`) → ردیف رزرو → redemption. کد قبل از درج سفارش قفل می‌شود چون FK `orders.discount_code_id` روی ردیف کد KEY SHARE می‌گیرد و `FOR UPDATE` بعدی deadlock می‌ساخت (بازبینی plan). استثنای سفارش جدید: ردیف آن قبل از advisory سفارش (داخل reserve) درج و flush می‌شود؛ بی‌خطر است چون تا commit برای دیگران دیده نمی‌شود. مسیرهای سفارش موجود (PAY-03، لغو، انقضا): advisory سفارش → ردیف سفارش.
- بررسی مسیرهای موجود: ثبت سفارش (کامل)؛ job انقضا (inventory → رزرو؛ سفارش/کد را قفل نمی‌کند)؛ اصلاح دستی موجودی (فقط inventory و رزروهای منقضی)؛ redemption (`redeem` روی کدی که از قبل قفل شده؛ `confirm`/`release` فقط ردیف redemption)؛ ویرایش ادمین کد (فقط کد)؛ نوشتن سبد و ادغام (سبد کاربر → سبد مهمان → خواندن variant)؛ state machine (فقط ردیف سفارش). هیچ مسیری inventory و بعد کد/سفارش را قفل نمی‌کند. تست همزمانی: دو خریدار با یک کد، آخرین استفاده کد، آخرین واحد، سفارش‌های متقاطع، همان کلید ×۳، و ثبت سفارش همزمان با اصلاح موجودی، ویرایش کد، job انقضا + لغو + release، و نوشتن سبد.
- الزام مسیرهای آینده: پرداخت موفق (PAY-03) و لغو مشتری/انقضا (ORD-06): ردیف سفارش → inventory (commit/release رزرو) → redemption؛ job انقضا هنگام لغو سفارش اول ردیف سفارش را با `SKIP LOCKED` قفل می‌کند (ADR-047).
- تصمیم‌های کم‌اثر (خودم؛ بازبینی opus): «یک سفارش pending» یعنی pending_payment با رزرو active و منقضی‌نشده؛ سفارش منقضی (که تا ORD-06 لغو نمی‌شود) مانع نمی‌شود و موجودی هم نگه نمی‌دارد. بررسی زیر lock سبد انجام می‌شود (درخواست‌های یک کاربر سریال‌اند). `now` بعد از lockها گرفته می‌شود؛ `created_at = updated_at = now`. fingerprint متفاوت → 409 `PRICE_CHANGED` با quote جدید و no-store؛ خطاهای build_quote (سبد، آدرس، روش، خط، کد) قبل از مقایسه fingerprint؛ `INSUFFICIENT_STOCK` فقط از reserve. replay همیشه همان 201 اولیه (حتی بعد از لغو). audit `order.created` بدون PII. سرآیند = Σ خطوط در service assert می‌شود.
- پیامدها: ORD-06، PAY-02..04، ACC-01، INV-06.

### ADR-049 — الزام‌های همه planهای PAY-* (دستور کاربر)
- تاریخ: 2026-10-18
- تصمیم (کاربر): تعبیر «یک سفارش pending زنده» در ADR-048 (رزرو active و منقضی‌نشده) پذیرفته شد و قید سخت‌تری لازم نیست. هر plan از PAY-* باید این موارد را داشته باشد:
  - interface برای adapter درگاه، به‌همراه gateway fake که فقط در dev و staging مجاز است. اگر در production، fake انتخاب شود، برنامه fail-closed می‌شود و بالا نمی‌آید. تبدیل تومان به ریال فقط داخل adapter انجام می‌شود (ADR-001).
  - callback ورودی نامطمئن است. پارامترهای آن هرگز مبنای حقیقت نیستند. verify سمت سرور با درگاه انجام می‌شود و مبلغ باید برابر `grand_total` باشد. idempotency با unique روی (gateway، ref) تضمین می‌شود. callback تکراری یا با ترتیب نادرست بی‌خطر است. endpoint آن rate limit دارد و داده کارت هرگز ذخیره نمی‌شود.
  - مسیر موفق در یک تراکنش و با ترتیب lock ADR-048 اجرا می‌شود: commit رزرو، confirm کد تخفیف، حذف خطوط سفارش‌داده‌شده از سبد، تنظیم وضعیت‌ها و audit. اگر commit نتیجه EXPIRED بدهد، مسیر refund_required اجرا می‌شود (D32).
  - job تطبیق: پرداخت‌هایی که بیش از N دقیقه pending مانده‌اند (callback گم‌شده) با درگاه verify می‌شوند. این job زیر advisory lock اجرا می‌شود.
  - تست‌ها: callback دوباره، callback بعد از لغو یا انقضا، مبلغ ناهمخوان، callback جعلی، و همزمانی پرداخت موفق با sweep انقضا.
- پیامدها: PAY-01..06، PAY-07.

### ADR-050 — لغو سفارش و لغو در انقضای رزرو (ORD-06)
- تاریخ: 2026-10-18
- تصمیم (کاربر): لغو مشتری با payment `unpaid` و `failed` مجاز است. با `pending` (مشتری در درگاه است) → 409 `PAYMENT_IN_PROGRESS`، تا لغو مشتری هرگز به `refund_required` نرسد. انقضا همیشه سفارش را لغو می‌کند (D32).
- تصمیم‌های کم‌اثر (خودم؛ بازبینی opus روی plan و diff):
  - `POST /orders/{id}/cancel`: ترتیب بررسی‌ها: 401 → 400 (path و query) → 404 (سفارش دیگران یا ناموجود؛ مالکیت قبل از advisory) → advisory سفارش → ردیف سفارش `FOR UPDATE` کامل. سفارش لغوشده → 200 با وضعیت فعلی، بدون نوشتن (idempotent). guard وضعیت قبل از هر اثر جانبی → 422. پاسخ `OrderStatusResponse` با no-store؛ نمای کامل در ACC-01. بدون Idempotency-Key.
  - منطق مشترک در `app/modules/orders/cancel.py`: رزرو active با `release()` موجود آزاد می‌شود (`now` بعد از lockهای inventory). اگر `released_at ≥ expires_at` باشد، یا رزرو از قبل `expired` باشد، لغو با reason `expired` و actor system ثبت می‌شود (انقضای lazy، D34). movement و audit `reservation.released` در این حالت actor مشتری و پرچم `expired: true` دارند. سرویس رزرو تغییر نکرد؛ فقط `order_lock_key` عمومی شد.
  - redemption با `RedemptionService.release` آزاد می‌شود و audit `discount.redemption_released` دارد (فقط id).
  - job انقضا (INV-06): رزرو سفارش‌دار با try-advisory → ردیف سفارش `SKIP LOCKED` → `expire()` → لغو در همان تراکنش. سفارش مشغول skip می‌شود و دور بعد بسته می‌شود. مرحله دوم sweep سفارش‌های `pending_payment` با رزرو بسته‌شده و بدون رزرو active/committed را با `expired` لغو می‌کند (job قدیمی یا deploy غلتان). `SweepResult.cancelled` اضافه شد.
  - invariant: هر مسیری که رزرو سفارش را بدون commit می‌بندد، سفارش را در همان تراکنش لغو می‌کند. **PAY-03:** شاخه EXPIRED از `commit()` باید با advisory → ردیف سفارش شروع شود و سفارش را در همان تراکنش لغو کند (`refund_required`، D32)؛ وگرنه مرحله دوم sweep یک دور دیرتر لغو می‌کند. مسیرهای انقضای lazy: فعلاً لغو؛ PAY-02/03 و ACC-01 (حداقل در نمایش) بعداً.
- پیامدها: PAY-02..04، ACC-01، ADM.

### ADR-051 — پرداخت (M3.5، PAY-01..06؛ تأیید کاربر با تغییرات)
- تاریخ: 2026-10-19
- تصمیم (کاربر):
  1. **مبلغ ناهمخوان:** verify نتیجه PAID می‌دهد ولی مبلغ ≠ `payment.amount` یا ≠ `grand_total`. در این حالت payment → `refund_required` با reason `amount_mismatch`، به‌همراه log ERROR و audit. رزرو مصرف نمی‌شود، سفارش باز می‌ماند (order payment → `failed`) و retry در مهلت ممکن است.
  2. **پاسخ callback:** به هر callback پردازش‌شده 200 داده می‌شود و نتیجه (`outcome`) در بدنه است (تکراری، PAID، FAILED، PENDING، mismatch، refund_required، duplicate). هدف جلوگیری از retry storm درگاه است. ref ناشناخته 404 می‌گیرد، rate limit 429 و بدنه نامعتبر 400.
  3. **init دوباره روی payment pending:** اگر session درگاه هنوز معتبر است (`gateway_expires_at` > now)، همان `redirect_url` برمی‌گردد. وگرنه payment قدیمی با درگاه verify و اعمال می‌شود؛ اگر باز هم pending ماند، `failed` (`superseded`) می‌شود و payment جدید ساخته می‌شود.
  4. **پرداخت دوم روی سفارش paid:** payment → `refund_required` (`duplicate_payment`) با audit و WARNING. سفارش، موجودی، سبد و redemption فقط یک بار اثر می‌گیرند.
  5. callback به شکل `POST` با JSON طبق PRD است. پشتیبانی GET redirect در PAY-07.
- تصمیم‌های کم‌اثر (خودم؛ بازبینی opus): جزئیات در [M3.5-PLAN.md](M3.5-PLAN.md).
  - جدول انتقال جدای ردیف payment.
  - order payment فقط با `check_transition` تغییر می‌کند.
  - ترتیب lock: سبد (`lock_user_cart`) → advisory → ردیف سفارش → ردیف payment → inventory → رزرو → redemption.
  - verify هرگز داخل تراکنش اجرا نمی‌شود.
  - state fake در Postgres نگه داشته می‌شود و ref ناشناخته PENDING برمی‌گرداند.
  - eventها ۹۰ روز نگه داشته می‌شوند.
  - کد سبد اگر همان کد سفارش باشد بعد از پرداخت موفق برداشته می‌شود.
  - سفارش با `grand_total = 0` در init → 422 (`zero_amount`؛ تأیید خودکار بدون درگاه به نسخه بعد موکول شد).
  - duplicate با همان کلید در حین فراخوانی درگاه → 409 `PAYMENT_IN_PROGRESS` (پاسخ هنوز ذخیره نشده؛ مثل رفتار رایج idempotency).
  - rate limit callback پشت proxy به OPS-04 نیاز دارد.
  - fail-closed: `build_payment_gateway` (و job تطبیق در startup) در production خطا می‌دهد، مثل SMS؛ نه در Settings، که هر config production را تا PAY-07 نامعتبر می‌کرد. شکست اولین درخواست پرداخت در production → 503 (PAY-02).
  - init (PAY-02):
    - session منقضی فقط با verify FAILED قطعی بسته می‌شود. verify PAID با `PaymentProcessor` همان‌جا اعمال می‌شود (PAY-03؛ prepare بعدی 422 `order_not_payable` می‌دهد، یا اگر نتیجه refund_required بود payment تازه می‌سازد)؛ verify PENDING → 409 `session_open`، چون درگاه هنوز session قدیمی را می‌پذیرد و payment جدید می‌توانست دو بار شارژ کند (تفسیر محافظه‌کارانه تصمیم ۳).
    - سفارش لغوشده با دلیل انقضا → 409 `RESERVATION_EXPIRED`.
    - هر خطای درگاه یا adapter payment در جریان را `failed` (`gateway_error`) می‌کند.
  - callback و اعمال نتیجه (PAY-03):
    - ترتیب lock: سبد کاربر سفارش → advisory → ردیف سفارش → ردیف payment → inventory → رزرو → redemption → خطوط سبد.
    - mismatch فقط وقتی order payment را تغییر می‌دهد که آن payment تلاش زنده سفارش بوده باشد (`failed`)، یا سفارش لغو شده باشد (`refund_required`). FAILED بعد از paid نادیده گرفته و log می‌شود.
    - بدنه callback قبل از خواندن محدود می‌شود (Content-Length، سپس stream تا ۸KB). بدنه نامعتبر ذخیره و شمرده نمی‌شود، فقط log می‌شود.
  - reconciliation (PAY-04):
    - با `PAYMENT_RECONCILE_SECONDS > 0` (پیش‌فرض 60)، gateway در startup ساخته می‌شود. نتیجه: **production بدون درگاه واقعی اصلاً بالا نمی‌آید** تا PAY-07 (fail-closed، ADR-049).
    - هر payment pending قدیمی‌تر از stale verify می‌شود. ref NULL → `request_lost`. verify PENDING وقتی now ≥ `gateway_expires_at` + stale → `abandoned`، برای هر سفارشی، نه فقط سفارش لغوشده؛ امن است چون PAID دیرهنگام بعد از آن همچنان refund_required یا duplicate می‌شود.
    - بعد از ۳ verify بی‌پاسخ پشت هم، دور متوقف می‌شود.
    - purge رویدادها حداکثر ساعتی یک بار انجام می‌شود.
    - `lock_user_cart` در apply ممکن است سبد خالی برای کاربر بسازد؛ مثل callback، بی‌خطر است.
  - چرخه عمر ردیف payment: `failure_reason` فقط در failed/refund_required است (`failed → paid` آن را پاک می‌کند؛ سابقه در event و audit)؛ refund_required همیشه `paid_at` دارد؛ `paid_amount` مبلغ تأییدشده درگاه به تومان است. reconciliation رویداد `verify` می‌نویسد.
- پیامدها: PAY-01..07، ADM (فیلتر `refund_required` و `failure_reason`)، HANDOFF-01 (redirect frontend).

### ADR-052 — تحویل به frontend: هم‌خوانی PRD، OpenAPI و قرارداد مرورگر (HANDOFF-01)
- تاریخ: 2026-10-25
- تصمیم (کاربر): تفسیر محافظه‌کارانه init دوباره (verify PENDING روی session منقضی → 409 `PAYMENT_IN_PROGRESS` `session_open`؛ ADR-051) تأیید شد.
- تصمیم‌های کم‌اثر (خودم؛ بازبینی opus):
  - **بازگشت از درگاه:** `PAYMENT_CALLBACK_URL` به صفحه نتیجه frontend اشاره می‌کند. frontend همان reference را با `POST /payments/callback` (JSON، طبق PRD و ADR-051) می‌فرستد و UI را از `outcome` می‌سازد. callback ورودی نامطمئن است، پس relay از مرورگر امن است. callback گم‌شده را reconciliation جبران می‌کند. redirect مستقیم GET/POST فرم درگاه واقعی در PAY-07.
  - **CORS (اصلاح bug):** `Idempotency-Key` به `allow_headers` اضافه شد؛ بدون آن preflight مرورگر `POST /orders` و `/payments/init` را رد می‌کرد. `Retry-After` به `expose_headers` اضافه شد تا frontend زمان 429 را بخواند.
  - `POST /orders`: بررسی query ناشناخته بعد از احراز هویت (401 قبل از 400)، مثل لغو و init.
  - **CORS در production (دستور کاربر):** `CORS_ORIGINS` باید origin(های) صریح frontend را داشته باشد. خالی یا تنظیم‌نشده باعث شکست startup می‌شود (`Settings`)، و `*` از قبل ممنوع بود. با origin صریح، credentials همیشه روشن است. نام setting همان `CORS_ORIGINS` موجود ماند تا configهای فعلی نشکنند.
  - **OpenAPI:** `docs/api/openapi.json` با `scripts/export_openapi.py` از تنظیمات ثابت development ساخته می‌شود (مستقل از `.env`؛ شامل endpointهای fake فقط-dev). تست `tests/test_api_contract.py` هم‌خوانی را بررسی می‌کند. نسخه‌بندی در OPS-06.
  - یادداشت‌های frontend در `docs/api/FRONTEND.md`: cookieها، single-flight refresh، Idempotency-Key، کدهای خطا، flagهای تغییر قیمت و outcomeهای پرداخت.
  - PRD فقط جایی اصلاح شد که با ADR تأییدشده مغایرت داشت (جدول PRD changes). بخش‌های قالبی آینده دست نخوردند، به‌جز یادداشت ارجاع در «انبار».
- پیامدها: PAY-07 (redirect درگاه واقعی)، ACC-01 (`GET /orders`)، OPS-06، ADM-00 («انبار»).

### ADR-053 — نیازمندی‌های فاز ۴: حساب، پنل مدیریت و محتوا (D35–D42؛ تصمیم کاربر)
- تاریخ: 2026-10-26
- تصمیم (کاربر تأیید کرد؛ ACC-00، ADM-00، CNT-00):
  - D35: task جدید ADM-08 بازپرداخت دستی را ثبت می‌کند. شرایط:
    - انتقال فقط `refund_required → refunded`، هم روی payment و هم روی order payment.
    - idempotent: همان reference → 200 بدون نوشتن؛ reference دیگر → 409.
    - فقط بازپرداخت کامل در v1؛ بازپرداخت جزئی موکول است.
    - `refund_reference` اجباری و unique است.
    - مجوز جدید `payments:refund` (admin و super_admin)، audit `payment.refunded` و بازبین opus.
    - لغو سفارش پرداخت‌شده توسط ادمین به مرجوعی (M6.4) موکول است.
  - D36: حذف `GET /home/sections` و `GET /categories/featured`. کالکشن (M6.1)، علاقه‌مندی (M6.3)، مقصد جست‌وجو (M6.2)، شخصی‌سازی و `deviceType` موکول شدند. تصویر موبایل جدا جایگزین `deviceType` است.
  - D37: حذف حساب کاربر موکول شد، چون به ناشناس‌سازی نیاز دارد (ADR-046). task backlog: ACC-05.
  - D38: فهرست مشتریان (و فهرست سفارش‌های ادمین) موبایل را ماسک می‌کند. جزئیات مشتری موبایل کامل را نشان می‌دهد و هر مشاهده audit `customer.viewed` دارد (بدون PII).
  - D39: مرز روز، هفته و ماه در داشبورد و گزارش‌ها به وقت `Asia/Tehran` است. ذخیره UTC می‌ماند.
  - D40: صفحه ایستا، FAQ و متن سکشن به‌صورت Markdown است. هر تگ HTML خام → 400.
  - D41: مقصد بنر و سکشن فقط داخلی است (`product`، `category`، `page`، `none`). لینک بیرونی → 400.
  - D42 (طراحی storefront E): خلاصه محصول در لیست‌ها و `/home` دو فیلد جدید دارد:
    - `color_swatches`: تا ۵ رنگ متمایز از تنوع‌های عمومی به ترتیب `display_order`، هر کدام `{value, hex}`. رنگ بدون hex با `hex: null` می‌آید.
    - `is_new`: محصول در `PRODUCT_NEW_DAYS` روز اخیر (پیش‌فرض ۳۰، `Settings`) ساخته شده است (`created_at`).
    - CAT-04 hex ندارد، پس migration ستون `hex` (nullable، فقط برای `color`، CHECK `^#[0-9A-F]{6}$`) را به `variant_options` اضافه می‌کند. این migration در task جدید CAT-18، در اولین batch فاز ۴ است.
- تصمیم‌های کم‌اثر (خودم):
  - Shipment یک جدول 1:1 با سفارش است (ADR-046). `shipped` کد رهگیری می‌خواهد و `delivered` سفارش را در همان تراکنش `completed` می‌کند.
  - ادمین فقط سفارش پرداخت‌نشده را لغو می‌کند (reason `admin`).
  - مجوز جدید `contact_messages:manage` (support، admin، super_admin).
  - rate limit فرم تماس: ۵ در ساعت برای هر IP و ۳ در ساعت برای هر موبایل.
  - گزارش‌ها فقط JSON هستند؛ مبنای زمان `paid_at` و بازه حداکثر ۳۶۶ روز.
  - داشبورد یک endpoint دارد (`reports:read`).
  - `GET /orders` چیزی نمی‌نویسد و `can_pay` و `can_cancel` را برمی‌گرداند (ADR-050).
- پیامدها: ACC-01، ACC-02، ADM-01..08، CNT-01..07، CAT-18، ACC-05.

### ADR-054 — ثبت بازپرداخت دستی: مبلغ و بازگشت بدهی (ADM-08؛ تصمیم کاربر)
- تاریخ: 2026-10-26
- زمینه: بازبینی plan ADM-08 (opus) دو مسئله پیدا کرد:
  - سفارش `refunded` می‌توانست `refund_required` بعدی را پنهان کند.
  - `paid_amount` گاهی NULL است (ریال بخش‌پذیر بر ۱۰ نیست).
- تصمیم (کاربر):
  1. اگر پرداخت دیگری از سفارش لغوشده `refunded` بعداً موفق شود، order payment به `refund_required` برمی‌گردد. انتقال جدید ADR-047: `refunded → refund_required`، با guard موجود «فقط سفارش cancelled». سفارش لغونشده تغییری نمی‌کند (تست).
  2. وقتی `paid_amount` NULL است، ادمین مبلغ پرداخت‌شده را وارد می‌کند: عدد صحیح مثبت تومان و ≤ `grand_total` سفارش. با `refund_amount_source = admin_entered` در ردیف payment و audit ذخیره می‌شود. نبود مبلغ → 422 `amount_required`.
- تصمیم‌های کم‌اثر (خودم؛ بازبینی opus):
  - با `paid_amount` معلوم، ارسال `amount` → 422 `amount_not_allowed` (فقط بازپرداخت کامل). CHECK در DB: `gateway` ⇒ `refund_amount = paid_amount`.
  - مبلغ بیش از جمع سفارش → 422 `amount_too_large`.
  - order payment فقط وقتی `refunded` می‌شود که هیچ payment دیگری از همان سفارش `refund_required` نباشد.
  - `refund_reference` با trim و بدون کاراکتر کنترلی ذخیره می‌شود و بین همه paymentها unique است (حساس به حروف). تکرار با همان reference → 200 بدون نوشتن؛ reference دیگر → 409.
  - تابع جدا `RefundService`، چون `move_payment` برای `refunded` ممنوع است. `failure_reason` و `paid_amount` حفظ می‌شوند و actor ادمین است.
  - downgrade migration `0027` با وجود ردیف refunded متوقف می‌شود.
  - روی دیتابیس‌های موجود `python -m app.db.seed` برای `payments:refund` دوباره اجرا شود.
- پیامدها: ADM-08، ADM-07 (ماتریس نقش)، ADM-04/05 (refunded فروش موفق نیست).

### ADR-055 — داشبورد و گزارش‌ها: مرز زمانی تهران و تقویم (ADM-04، ADM-05)
- تاریخ: 2026-10-26
- تصمیم (کاربر، ADM-05): در `group_by` هفته از شنبه شروع می‌شود و ماه شمسی (جلالی) است. روزها در SQL جمع می‌شوند و در Python با یک تبدیل جلالی خالص (unit test، بدون dependency) به هفته و ماه تبدیل می‌شوند.
- تصمیم‌های کم‌اثر (خودم؛ بازبینی opus):
  - تبدیل زمان تهران در PostgreSQL با `timezone('Asia/Tehran', …)` انجام می‌شود. `zoneinfo` روی Windows بدون بسته `tzdata` داده ندارد و dependency جدید لازم نیست.
  - فروش با `paid_at` اولین payment موفق سفارش تاریخ‌گذاری می‌شود (HAVING، نه WHERE، تا payment تکراری بعدی تاریخ سفارش قدیمی را عوض نکند).
  - «۷ روز» یعنی امروز تهران و ۶ روز قبل، از نیمه‌شب تهران تا `generated_at`. «۳۰ روز» به همین شکل.
  - هشدار موجودی فقط تنوع‌های فعال و حذف‌نشده محصول حذف‌نشده را می‌شمارد (برخلاف فهرست موجودی INV-08 که تنوع غیرفعال را هم نشان می‌دهد).
  - مشتری جدید = کاربر حذف‌نشده با نقش `customer` که `created_at` در بازه است.
  - شاخص‌های صف کار (`pending_payment` با رزرو زنده، `refund_required`، آماده ارسال، موجودی) لحظه‌ای هستند، نه per بازه.
  - گزارش‌ها: `from`/`to` تاریخ تهران (نیمه‌باز)؛ bucket با `label` جلالی (`YYYY-MM-DD` روز اول روز/هفته، `YYYY-MM` ماه) و برش به بازه؛ bucket خالی هم می‌آید.
  - گزارش دسته از دسته فعلی محصول است (snapshot دسته در خط نیست)؛ عنوان محصول آخرین snapshot؛ `limit` محصول 1..100 (پیش‌فرض 20) و totals همه گروه‌ها را می‌شمارد.
- پیامدها: ADM-04، ADM-05.

### ADR-056 — صفحه ایستا، FAQ و فرم تماس (CNT-04، CNT-05، CNT-06)
- تاریخ: 2026-11-11
- تصمیم‌های کم‌اثر (خودم):
  - HTML خام (D40) یعنی هر `<` که parser HTML آن را شروع تگ، comment یا declaration بداند (`<x`، `</x`، `<!`، `<?`)، حتی داخل code span یا autolink. `a < b` مجاز است. کاراکتر کنترلی هم رد می‌شود (به‌جز newline و tab).
  - slug صفحه بعد از ایجاد ثابت است (PATCH با slug → 400). `published_at` اولین انتشار است و با برگشت به draft پاک نمی‌شود. audit متن کامل صفحه را نگه می‌دارد تا تغییر متن قوانین قابل پیگیری باشد.
  - پاسخ FAQ حداکثر ۵٬۰۰۰ کاراکتر است. گروه‌ها به ترتیب اولین پرسششان می‌آیند.
  - فرم تماس: فقط انتقال‌های `new → in_progress` و `in_progress → closed` مجازند (مثلاً `new → closed` → 422). وضعیت یکسان no-op است. audit فقط وضعیت و `internal_note_changed` را دارد، نه متن پیام یا یادداشت. IP در پاسخ ادمین نمی‌آید.
  - سقف‌های تماس با advisory lock روی کلیدهای IP و موبایل (به ترتیب مرتب) دقیق هستند. `Retry-After` زمان خروج قدیمی‌ترین پیام شمرده‌شده از پنجره است. تنظیمات: `CONTACT_WINDOW_SECONDS`، `CONTACT_MAX_PER_IP`، `CONTACT_MAX_PER_PHONE`.
  - مجوز `contact_messages:manage` با seed اضافه می‌شود. بعد از استقرار، `python -m app.db.seed` دوباره اجرا شود.
- پیامدها: CNT-04، CNT-05، CNT-06.

### ADR-057 — سرعت CI: uv، cache لایه docker و path filter (تصمیم کاربر)
- تاریخ: 2026-11-13
- زمینه: دو run در 2026-11-11 حدود ۱۲ ساعت بدون job در صف GitHub ماندند و نه cancel شدند نه rerun. repo عمومی است، پس سقف دقیقه علت نبود. یک commit خالی `ci: retrigger` run تازه را بلافاصله شروع کرد. بعد از آن، plan کاهش زمان CI بررسی شد.
- تصمیم (کاربر):
  - ثابت می‌ماند: suite کامل و staging-smoke روی هر push. ADR-037 و قاعده «CI سبز بعد از هر push» تغییر نمی‌کنند. اجرای فقط تست‌های سریع روی push رد شد.
  - نصب در CI با `uv pip install --system --require-hashes` از همان `requirements-dev.lock`. خود uv اول با pip و hash خودش از همان lock نصب می‌شود (SEC-06 حفظ می‌شود). wheelها با `actions/cache` و کلید hash lock cache می‌شوند.
  - image API در staging-smoke و publish-image با `docker/build-push-action` و `cache-from/to: type=gha` (scope `api`) ساخته می‌شود. staging با `compose up --no-build` همان image را با نام `project-ak-staging-api` اجرا می‌کند.
  - push که فقط `FRONTEND/**` یا `**/*.md` را تغییر دهد CI بک‌اند ندارد (`paths-ignore`). روی PR هیچ فیلتری نیست.
  - uv و buildx ابزار CI هستند، نه dependency برنامه. uv از قبل در lock dev بود (`scripts/lock.py`).
- پیامد: commit فقط-سند (مثلاً به‌روزرسانی PROGRESS و task به‌تنهایی) CI ندارد. commitهای task همیشه کد هم دارند، پس CI می‌گیرند.

### ADR-058 — موکول شدن D8، D9، D10 و D13؛ production مسدود (تصمیم کاربر)
- تاریخ: 2026-11-13
- تصمیم (کاربر): انتخاب درگاه پرداخت واقعی (D8)، SMS provider (D9)، file storage (D10) و محیط production (D13) به بعد موکول شد. بقیه فاز ۵ انجام می‌شود.
  - وضعیت جدید `DEFERRED`: PAY-07، OPS-04، OPS-05، OPS-07 و DEC-08، DEC-09، DEC-10، DEC-13 (جمعاً 17h). از درصد و forecast حذف می‌شوند (مثل CANCELLED)، ولی در PLAN می‌مانند.
  - دروازه فاز ۵ وقتی همه taskهای غیر-DEFERRED آن COMPLETE باشند بسته می‌شود. خروجی آن یک image آماده staging (`phase-5`) است، نه انتشار production.
  - **production go-live مسدود است** تا هر چهار تصمیم گرفته شود و PAY-07، OPS-04، OPS-05 و OPS-07 COMPLETE شوند. کد همین الان fail-closed است:
    - درگاه: `build_payment_gateway` در production خطا می‌دهد. با job تطبیق (پیش‌فرض روشن) برنامه اصلاً بالا نمی‌آید، و بدون آن هر endpoint پرداخت 503 `PAYMENT_GATEWAY_UNAVAILABLE` می‌دهد (ADR-049).
    - SMS: `build_sms_sender` در production خطا می‌دهد، پس هیچ OTPی ارسال نمی‌شود.
    - storage: `MEDIA_STORAGE=memory` در production با خطای `Settings` رد می‌شود. `local` مجاز است، ولی انتخاب نهایی D10 است.
    - OPS-10 این سه رفتار را با تست قرارداد قفل می‌کند.
  - providerها پشت interface با پیاده‌سازی fake یا dev می‌مانند (ADR-009): `PaymentGateway` و `FakeGateway`، `SmsSender` و `FakeSmsSender`، `FileStorage` با `LocalFileStorage` و `InMemoryFileStorage`. OPS-10 یک suite قرارداد مشترک اضافه می‌کند تا adapter واقعی آینده فقط با پاس کردن همان suite وارد شود.
- پیامدها: PLAN، ROADMAP، PROGRESS (forecast از 2026-11-13)، OPS-10، دروازه فاز ۵.

### ADR-059 — audit_logs فقط-افزودنی در دیتابیس (SEC-04)
- تاریخ: 2026-11-13
- تصمیم (خودم؛ بازبین مستقل plan را تأیید کرد):
  - migration `0033` برای UPDATE و TRUNCATE روی `audit_logs` trigger اضافه می‌کند. DELETE از `0001` رد می‌شد. هر سه با SQLSTATE `23000` رد می‌شوند.
  - تنها UPDATE مجاز، `ON DELETE SET NULL` کلید `actor_user_id` است، وقتی کاربری hard delete شود. trigger بررسی می‌کند که به‌جز همان ستون هیچ چیز دیگری عوض نشده باشد. این عمداً اجازه پاک شدن هویت actor (PII) با حذف کاربر را می‌دهد (ADR-046)، ولی متن audit دست نمی‌خورد.
  - هر سه trigger با `ENABLE ALWAYS` فعال‌اند، پس `session_replication_role = replica` هم آن‌ها را دور نمی‌زند.
- ریسک باقی‌مانده: مالک جدول یا superuser می‌تواند trigger را disable یا drop کند. الان در compose و staging، برنامه با همان نقشی اجرا می‌شود که migrationها را اجرا می‌کند و مالک جدول است. راه‌حل این است که در production برنامه با نقش غیرمالک اجرا شود و migration با نقش مالک جدا. این در OPS-04 (DEFERRED، ADR-058) انجام می‌شود و پیش‌شرط production است.
- پیامدها: SEC-04، OPS-04.

### ADR-060 — نیازمندی‌های فاز ۵: امنیت، پذیرش و پایش (SEC-00، OPS-00؛ تصمیم کاربر)
- تاریخ: 2026-11-13
- تصمیم (کاربر پیش‌نویس `M5-REQUIREMENTS-DRAFT` را بدون تغییر تأیید کرد):
  - Q1: شمارنده سقف سراسری در حافظه هر پروسه است، بدون Redis. سقف per-instance است.
  - Q2: `/metrics` با `METRICS_TOKEN` (bearer) محافظت می‌شود و بدون آن 404 است.
  - Q3: `/docs`، `/redoc` و `/openapi.json` فقط در production خاموش‌اند.
  - Q4: سقف پیش‌فرض بدنه ۱MB است. رسانه ۵MB و callback ۸KB جدا می‌مانند.
  - Q5: interface ردیابی خطا با پیاده‌سازی log-only. provider واقعی همراه D13 موکول است.
- تصمیم‌های کم‌اثر اجرای SEC-02 (خودم؛ بازبین مستقل تأیید کرد):
  - ترتیب middlewareها از بیرون به داخل: هدرهای امنیتی، CORS، `RequestContext`، سقف درخواست، سقف بدنه. پس 413 و 429 هم `request_id`، CORS و هدرهای امنیتی دارند.
  - پاسخ 500 خطای پیش‌بینی‌نشده را `ServerErrorMiddleware` خود Starlette می‌سازد که بیرون همه این‌هاست، پس هدرهای امنیتی و CORS ندارد. بدنه JSON است و ریسکش کم است.
  - سقف multipart دو برابر سقف آپلود است، تا endpointهای آپلود ترتیب CAT-05 را حفظ کنند: اول auth (401/403)، بعد 400 برای فایل بیش از سقف خودشان. بدنه chunked بعد از عبور از سقف قطع می‌شود و 413 جای پاسخ app را می‌گیرد. `Content-Length` نامعتبر → 400.
  - CSP صفحه `/docs` و `/redoc` (فقط خارج از production) CDN مستندات را مجاز می‌کند. `/openapi.json` همان CSP سخت را دارد.
- پیامدها: PRD (چهار بخش ✓)، SEC-01، SEC-02، SEC-03، OPS-01، OPS-02، OPS-03.

### تصمیم‌های deferred
- **D8، D9، D10، D13:** به تصمیم کاربر موکول شدند (ADR-058). production تا آن موقع مسدود است.

## PRD changes

| تاریخ | بخش | تغییر | تصمیم مرجع |
|---|---|---|---|
| 2026-09-29 | «معماری سیستم» | ProductVariant بدون موجودی؛ نقش‌های support و content_manager اضافه؛ Finance/Warehouse Manager موکول | D3، D2 |
| 2026-09-29 | «هویت و دسترسی» | نقش‌های support و content_manager؛ refresh در cookie HttpOnly/Secure/SameSite=Strict، access در body | D2، D16 |
| 2026-09-29 | «قیمت و مالیات» | `/cart/recalculate` و `/checkout/validate-pricing` با `POST /checkout/validate` جایگزین شد؛ Finance Manager موکول | D5، D2 |
| 2026-09-29 | «موجودی و رزرو» | رزرو در `POST /orders`؛ endpointهای عمومی reservation و `validate-stock` حذف؛ 410 → 409 `RESERVATION_EXPIRED`؛ یک انبار پیش‌فرض؛ Warehouse Manager موکول | D6، D5، D7، D3، D4، D2 |
| 2026-09-29 | «صفحه اصلی» | موجودی از ProductVariant حذف؛ Content Admin → Content Manager | D3، D2 |
| 2026-09-29 | «دسته‌بندی محصولات» | موجودی از ProductVariant حذف؛ Content Admin → Content Manager | D3، D2 |
| 2026-10-09 | «جزئیات محصول» ✓، «محصولات» ✓، «معماری سیستم» | بازنویسی دو بخش قالبی (CAT-00)؛ `GET /products/{id}` → `GET /products/{slug}` | D24 (ADR-020) |
| 2026-10-10 | «دسته‌بندی محصولات» ✓ | افزودن `GET /categories` (درخت)؛ قاعده پنهان‌شدن با جد غیرفعال؛ مجوز `categories:edit_content` برای content_manager | D26 (ADR-022)، D27 (ADR-023) |
| 2026-10-10 | «دسته‌بندی محصولات» ✓ | افزودن `DELETE /admin/categories/{id}` (حذف نرم، 409 با زیرمجموعه یا محصول) | ADR-025 |
| 2026-10-10 | «دسته‌بندی محصولات» ✓، «محصولات» ✓ | `imageUrl` دسته → `imageMediaId`؛ افزودن `POST /admin/media`؛ ProductMedia با `mediaId` به Media | ADR-028 |
| 2026-10-12 | «سبد خرید»، «ورود یا خرید مهمان»، «آدرس»، «شیوه ارسال»، «کد تخفیف»، «پرداخت»، «نتیجه سفارش»، «مدیریت سفارش»، «تخفیف‌ها» (همه ✓) | بازنویسی نه بخش قالبی (CART-00، DSC-00، ADDR-00، ORD-00، PAY-00)؛ CRUDهای قالبی و CheckoutSession حذف شدند | D30–D34 (ADR-039) |
| 2026-10-12 | «قیمت و مالیات» ✓ | `POST /orders/{id}/recalculate` به نسخه بعد موکول شد | D33 (ADR-039) |
| 2026-10-25 | «معماری سیستم»، «هویت و دسترسی»، «قیمت و مالیات»، «موجودی و رزرو»، «سبد خرید»، «ورود یا خرید مهمان»، «شیوه ارسال»، «کد تخفیف»، «پرداخت»، «نتیجه سفارش»، «تخفیف‌ها»، «انبار» (یادداشت) | هم‌خوانی با کد (HANDOFF-01): قرارداد snake_case و 429/503؛ دسترسی پنل با permission؛ چرخش refresh و reuse detection؛ CartPriceSnapshot حذف و flagهای per-line؛ فیلدهای OrderItem/OrderPriceSnapshot/Order/Payment؛ شکست پرداخت رزرو را نگه می‌دارد؛ `acknowledge-prices`؛ وضعیت `converted` سبد حذف؛ callback همیشه 200 با `outcome`، mismatch و duplicate → refund_required، init دوباره و 503؛ `ORDER_PENDING`، لغو با payment pending → 409، `GET /orders` در ACC-01؛ انتقال‌های payment؛ درصد کد به basis point | ADR-017–019، ADR-038، ADR-040–048، ADR-050–052 |
| 2026-10-26 | «پروفایل»، «سفارش‌ها»، «داشبورد»، «مشتریان»، «گزارش‌ها»، «گزارش ممیزی»، «محتوا و بنرها»، «درباره برند»، «تماس با ما»، «سؤالات متداول»، «قوانین و حریم خصوصی» (همه ✓)؛ «مدیریت سفارش» ✓ و «صفحه اصلی» ✓ (تکمیل)؛ «دسته‌بندی محصولات» ✓ (کارت) | بازنویسی یازده بخش قالبی (ACC-00، ADM-00، CNT-00)؛ بازپرداخت دستی و Shipment؛ کاهش scope صفحه اصلی؛ `color_swatches` و `is_new` | D35–D42 (ADR-053) |
| 2026-11-13 | «حالت‌های رابط»، «امنیت»، «تست و پذیرش»، «پایش و رخدادها» (همه ✓) | بازنویسی چهار بخش قالبی؛ سقف سراسری درخواست، هدرهای امنیتی، سقف بدنه، خاموشی مستندات API در production، معیار آماده بودن نسخه، متریک و هشدار و پشتیبان؛ endpointهای قالبی حذف شدند (SEC-00، OPS-00) | ADR-060 |

قاعده: هر task نوع `XX-00` بخش قالبی ماژول خود را در PRD بازنویسی می‌کند، به عنوان آن بخش «✓ بازبینی‌شده» اضافه می‌کند و یک ردیف به این جدول می‌افزاید.

_قالب ADR جدید:_

```
### ADR-NNN — عنوان (Dn)
- تاریخ: YYYY-MM-DD
- زمینه:
- تصمیم:
- پیامدها:
```
