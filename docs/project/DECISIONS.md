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
  - رزرو منقضی تا آزادسازی هنوز موجودی را اشغال می‌کند (جهت محافظه‌کارانه؛ oversell ممکن نیست). هر مسیر نوشتنی (سبد، `POST /checkout/validate`، `POST /orders`) قبل از محاسبه free، رزروهای منقضی همان آیتم‌ها را زیر همان lock آزاد می‌کند (PRD: «در اولین بررسی آزاد شود»)، به‌علاوه sweep دوره‌ای (INV-06). نمایش فقط‌خواندنی ممکن است کمی کهنه باشد، فقط در جهت کمتر.
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

قاعده: هر task نوع `XX-00` بخش قالبی ماژول خود را در PRD بازنویسی می‌کند، به عنوان آن بخش «✓ بازبینی‌شده» اضافه می‌کند و یک ردیف به این جدول می‌افزاید.

_قالب ADR جدید:_

```
### ADR-NNN — عنوان (Dn)
- تاریخ: YYYY-MM-DD
- زمینه:
- تصمیم:
- پیامدها:
```
