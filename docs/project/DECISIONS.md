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
| 2026-10-09 | «جزئیات محصول» ✓، «محصولات» ✓، «معماری سیستم» | بازنویسی دو بخش قالبی (CAT-00)؛ `GET /products/{id}` → `GET /products/{slug}` | D24 (ADR-020) |
| 2026-10-10 | «دسته‌بندی محصولات» ✓ | افزودن `GET /categories` (درخت)؛ قاعده پنهان‌شدن با جد غیرفعال؛ مجوز `categories:edit_content` برای content_manager | D26 (ADR-022)، D27 (ADR-023) |
| 2026-10-10 | «دسته‌بندی محصولات» ✓ | افزودن `DELETE /admin/categories/{id}` (حذف نرم، 409 با زیرمجموعه یا محصول) | ADR-025 |
| 2026-10-10 | «دسته‌بندی محصولات» ✓، «محصولات» ✓ | `imageUrl` دسته → `imageMediaId`؛ افزودن `POST /admin/media`؛ ProductMedia با `mediaId` به Media | ADR-028 |
| 2026-10-12 | «سبد خرید»، «ورود یا خرید مهمان»، «آدرس»، «شیوه ارسال»، «کد تخفیف»، «پرداخت»، «نتیجه سفارش»، «مدیریت سفارش»، «تخفیف‌ها» (همه ✓) | بازنویسی نه بخش قالبی (CART-00، DSC-00، ADDR-00، ORD-00، PAY-00)؛ CRUDهای قالبی و CheckoutSession حذف شدند | D30–D34 (ADR-039) |
| 2026-10-12 | «قیمت و مالیات» ✓ | `POST /orders/{id}/recalculate` به نسخه بعد موکول شد | D33 (ADR-039) |

قاعده: هر task نوع `XX-00` بخش قالبی ماژول خود را در PRD بازنویسی می‌کند، به عنوان آن بخش «✓ بازبینی‌شده» اضافه می‌کند و یک ردیف به این جدول می‌افزاید.

_قالب ADR جدید:_

```
### ADR-NNN — عنوان (Dn)
- تاریخ: YYYY-MM-DD
- زمینه:
- تصمیم:
- پیامدها:
```
