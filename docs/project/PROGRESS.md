# PROGRESS — منبع واحد «کجاییم؟»

**Last Updated:** 2026-10-09

## Current / Next
- **Phase › Milestone:** 2 Core domain › M2.1 Auth & RBAC
- **Current Task:** AUTH-12 — Auth API & security test suite · IN_PROGRESS (batch AUTH-11/12؛ AUTH-11 COMPLETE) → [tasks/phase-02/AUTH-12-auth-security-tests.md](../../tasks/phase-02/AUTH-12-auth-security-tests.md)
- **Status:** فاز ۱ کامل است و در `master` merge شد (PR #2 و PR #3؛ `master` = `1b5d92e`). فاز ۲ در جریان است؛ SEC-05 (gitleaks در CI) COMPLETE شد.
- **Progress:** 35/143 task COMPLETE · وزنی 18.0% (74.5h / 414h) · MVP 27.4%
- **Blockers:** فاز ۲ مانعی ندارد. در فاز ۵: D8، D9، D10 (انتخاب provider واقعی) و D13.
- **Next Action:** CI batch AUTH-08/10/09 سبز است. batch بعدی پیشنهادی: AUTH-11 + AUTH-12 (HIGH). SEC-06 در اولین batch بدون task HIGH اجرا می‌شود. سابقه PR فاز ۱: [PR-phase-1.md](PR-phase-1.md).
- **Branch:** `feat/phase-2-core-domain` (از `master` در `1b5d92e`). در پایان فاز ۲ با PR در `master` merge می‌شود. شاخه فاز ۱ (`feat/m1.1-repo-foundation`) کاملاً merge شده است.
- **Stale branch:** `backend` (local و `origin/backend`، commit `48f1542`) قدیمی است و کاملاً در `master` merge شده (commit اضافه‌ای ندارد). طبق دستور کاربر دست‌نخورده می‌ماند و روی آن کار نمی‌کنیم.

---

## Overall Progress
**18.0%** = 74.5h COMPLETE / 414h planned (estimate). **روش:** وزن‌دهی بر اساس ساعت برآوردی (CANCELLED حذف می‌شود).

## Phase Progress
| Phase | Status | Est. | Complete | % | Deadline (پیش‌بینی) |
|---|---|---|---|---|---|
| 1 Foundation | COMPLETE | 37h | 37h | 100% | 2026-10-09 |
| 2 Core domain | IN_PROGRESS | 134h | 37h | 27.6% | 2026-12-07 |
| 3 Purchase flow | NOT_STARTED | 100.5h | 0.5h | 0.5% | 2027-01-23 |
| 4 Account & admin | NOT_STARTED | 61h | 0 | 0% | 2027-02-20 |
| 5 Release | NOT_STARTED | 43h | 0 | 0% | 2027-03-12 |
| 6 Post-core | NOT_STARTED | 38.5h | 0 | 0% | 2027-03-30 |

## Deadlines & Schedule
- فرض (قابل تغییر): تنها، پاره‌وقت، ۱۵ ساعت در هفته، بدون ددلاین سخت. همه ددلاین‌ها **پیش‌بینی** هستند.
- باقی‌مانده: 339.5h ≈ ۲۳ هفته. MVP باقی‌مانده: 197h ≈ ۱۴ هفته.
- **Verdict:** on track نسبت به forecast (بدون buffer).

## Completed Recently
- 2026-10-09: AUTH-11 (admin user list/status/role, last super_admin guard, warehouse_manager data migration; ADR-019).
- 2026-10-09: AUTH-09 (GET /auth/me, PATCH /users/me, audit user.profile_updated, no-store).
- 2026-10-06: AUTH-10 (get_current_user, require_permission, ensure_owner; per-request DB checks; ADR-018).
- 2026-10-06: AUTH-08 (POST /auth/logout, idempotent, cookie cleared, audit auth.logout).
- 2026-10-06: AUTH-07 (POST /auth/refresh, rotation + family reuse detection; ADR-017).
- 2026-10-06: AUTH-06 (POST /auth/verify-otp, sessions, JWT HS256, refresh cookie; ADR-017).
- 2026-10-06: AUTH-05 (POST /auth/request-otp, per-mobile/IP/global 429; ADR-016).
- 2026-10-06: AUTH-02 (RBAC seed: 5 roles, 15 permission keys, role mapping).
- 2026-10-06: AUTH-04 (SmsSender interface + FakeSmsSender, zero-padded OTP generator).
- 2026-10-06: AUTH-03 (OtpCode model, HMAC-SHA256 with OTP_HASH_SECRET).
- 2026-10-06: AUTH-01 (User model aligned with PRD; E.164 phone + partial unique).
- 2026-10-06: SEC-05 (Secret scanning in CI, gitleaks 8.30.1).
- 2026-09-29: INF-05 (AuditLog writer service). فاز ۱ کامل شد.
- 2026-09-29: INF-06 (Sensitive-data redaction in logs).
- 2026-09-29: FND-07 (CI pipeline).
- 2026-09-29: FND-06 (Reproducible test database recipe).
- 2026-09-29: INF-04 (Soft delete mixin & helpers)؛ DEC ثبت‌شده: D19 (ADR-015).
- 2026-09-29: INF-03 (Page/limit pagination, sort & query-param allowlist).
- 2026-09-29: INF-01 (Error code catalog, domain errors, validation → 400).
- 2026-09-29: INF-02 (Integer-Toman money utilities)؛ DEC ثبت‌شده: D18 (ADR-014).
- 2026-09-29: FND-03 (Docker/Compose end-to-end).
- 2026-09-29: DEC-01، DEC-02، DEC-03، DEC-04، DEC-05، DEC-06، DEC-07، DEC-11، DEC-12، DEC-16 (ADR-003 تا ADR-013).
- 2026-09-13: FND-01، FND-02، FND-04، FND-05 (تأیید با اجرای تست‌ها در 2026-09-29).

## Remaining Work
- فاز ۱: هیچ (در `master` merge شده).
- فاز ۲ تا ۶: طبق [PLAN.md](PLAN.md).

## Blockers
| Blocked task | Cause |
|---|---|
| PAY-07 | D8 — انتخاب درگاه واقعی (قبل از فاز ۵) |
| OPS-05 | D9 — انتخاب SMS provider (قبل از فاز ۵) |
| OPS-07 | D10 — انتخاب file storage (قبل از فاز ۵) |
| OPS-04 | D13 — محیط production (deferred به فاز ۵) |

---

## Plan changes
### 2026-10-09 — تأیید batch AUTH-11/12 (تصمیم کاربر)
- admin مجوز `users:manage` را می‌گیرد (ADR-004 به‌روز شد). admin فقط وضعیت کاربرانی را تغییر می‌دهد که نقش‌هایشان زیرمجموعه `{customer}` است. هر نقش staff فقط با super_admin تغییر می‌کند (ADR-019).
- تغییر نقش با `{"roles": [...]}` کل مجموعه را جایگزین می‌کند. تغییر وضعیت یا نقش خود → 422. حذف یا غیرفعال‌کردن آخرین super_admin → 409. برآوردها تغییر نکرد.
### 2026-10-09 — بعد از CI سبز batch AUTH-08/10/09 (تصمیم کاربر)
- اصلاح audit: diff روی مقادیر خام ساخته می‌شود، هر ردیف `"changed": true` دارد و ماسک بعد از diff اعمال می‌شود (`field_masks`). این برای همه audit ها اعمال شد (INF-05).
- `email-validator` با range pin می‌ماند.
- task جدید SEC-06 (MEDIUM، 2h): lock file با hash، و نصب CI و Dockerfile از آن. در اولین batch بدون task HIGH اجرا می‌شود. کل برنامه 414h و فاز ۲ 134h شد.
### 2026-10-09 — تأیید batch AUTH-08/10/09 (تغییرات کاربر)
- access token با revoke شدن session فوراً باطل می‌شود و `email-validator` با deliverability خاموش pin شد (ADR-018).
- اضافه به AUTH-09: audit `user.profile_updated` با diff ماسک‌شده و `Cache-Control: no-store` روی ۵ endpoint auth/profile همراه با تست. برآورد تغییر نکرد.
### 2026-10-06 — تأیید batch AUTH-06/07 (تغییرات کاربر)
- حساب soft-deleted با وضعیت `blocked` مانع ساخت حساب جدید با همان شماره است (403). حساب حذف‌شده‌ی عادی باعث ساخت حساب جدید می‌شود (ADR-017).
- یادداشت برای بعد (فعلاً کاری انجام نمی‌شود): DSC-01 سقف استفاده per-user را با موبایل نرمال‌شده می‌شمارد. AUTH-10 وضعیت فعال‌بودن کاربر را در هر درخواست از دیتابیس می‌خواند. HANDOFF-01: frontend باید refresh را در همه تب‌ها single-flight کند.
### 2026-10-06 — scope جدید AUTH-11 (تصمیم کاربر)
- data migration برای حذف `warehouse_manager`: حذف فقط وقتی انجام می‌شود که `user_roles` به آن ارجاع نداشته باشد، و downgrade ردیف را دوباره insert می‌کند. تخصیص نقش فقط نقش‌های `DEFAULT_ROLES` را می‌پذیرد. برآورد AUTH-11 از 4h به 5h رسید و کل برنامه 412h شد.
- CI batch AUTH-02/05 سبز است.
### 2026-10-06 — تأیید batch AUTH-02/05 (تغییرات کاربر) و قواعد فرایند
- AUTH-02: نگاشت نقش به permission تأیید شد. ردیف `warehouse_manager` فقط یک‌بار و دستی از دیتابیس توسعه حذف شد (نه با seed).
- AUTH-05: محدودیت‌ها: cooldown 60s، ۵ درخواست در ساعت برای هر شماره، ۶۰ در ساعت برای هر IP (به‌خاطر CGNAT در ایران). سقف سراسری `OTP_MAX_GLOBAL_PER_HOUR=500` با 429 و لاگ WARNING `otp.global_cap_hit` اضافه شد. فیلد اضافه در body → 400. trusted-proxy مربوط به OPS-04 است.
- CLAUDE.md: سؤال کم‌اثر با پیشنهاد خودم تصمیم و در DECISIONS.md ثبت می‌شود. batch بدون task HIGH تا ۱۲ ساعت مجاز است و با «ok» تأیید می‌شود.
### 2026-10-06 — تأیید batch AUTH-01/03/04 (تغییرات کاربر)
- AUTH-01: موبایل فقط به شکل E.164 (`+989XXXXXXXXX`) با CHECK دیتابیسی؛ `normalize_phone()` اضافه شد. `email` در v1 unique نیست.
- AUTH-03: `otp_codes.mobile` هم همین فرمت و CHECK را دارد. کلید HMAC یک setting جدا به اسم `OTP_HASH_SECRET` است (حداقل ۳۲ کاراکتر). در production نبودن یا کوتاه‌بودن آن باعث fail شدن startup می‌شود.
- AUTH-04: mock OTP در production startup را fail می‌کند (fail-closed). کد OTP یک رشته ۶ کاراکتری zero-padded است.
- یادداشت برای بعد (فعلاً کاری انجام نمی‌شود): task پاک‌سازی دوره‌ای `otp_codes` در فاز OPS اضافه شود.

### 2026-09-30 — SEC-05: secret scanning در CI
- task جدید **SEC-05** (فاز ۲، M2.1، Level MEDIUM، 2h): gitleaks در CI با نسخه pin‌شده، fail روی هر finding و allowlist فقط برای fixtureهای ساختگی. اولین task فاز ۲ و پیش‌نیاز AUTH-06. کل: 142 task و 411h؛ فاز ۲: 131h؛ forecast فازهای ۲ تا ۶ یک روز جلو رفت.
### 2026-09-29 — INF-05: SEC-04 و trusted-proxy
- task جدید **SEC-04** (فاز ۵، Level HIGH، 2h): append-only در سطح DB برای `audit_logs` (trigger بلاک UPDATE؛ trigger بلاک DELETE از FND-04 موجود است) + تست integration. کل: 141 task، 409h؛ فاز ۵: 43h؛ forecast فاز ۵ و ۶ یک روز جلو رفت.
- معیار **OPS-04**: پیکربندی trusted-proxy تا IP در audit و log، IP واقعی کلاینت باشد و headerهای forwarded فقط از proxyهای تنظیم‌شده پذیرفته شوند.
- اصلاح: جمع «Overall Progress» (قبلاً 8.8% / 36h) با هدر هماهنگ شد.
### 2026-09-29 — INF-06: شماره سفارش
- **ORD-01:** معیار پذیرش جدید: شماره سفارش قالبی دارد که نمی‌تواند شبیه شماره موبایل باشد (مثلاً `ORD-YYYY-NNNNNN`). دلیل: mask موبایل در log ترجیحاً بیش از حد mask می‌کند (فقط رقم مجاور مانع mask است).

### 2026-09-29 — INF-04: soft delete و قاعده شاخه
- **SD rule** (سرآیند PLAN.md و یک خط در CLAUDE.md): read عمومی (list/detail) رکورد soft-deleted را برنمی‌گرداند (detail → 404 `NOT_FOUND`) و write ارجاع‌دهنده آن را رد می‌کند. «SD rule (test)» به معیار این taskها اضافه شد: CAT-06، CAT-07، CAT-08، CAT-09، CAT-11، CAT-14، CAT-16، INV-07، PRC-04، CART-02، ORD-03، ORD-04، ORD-06، CNT-01، CNT-02 و ACC-04.
- **AUTH-01:** ستون DB همان `phone` می‌ماند و فیلد API طبق PRD `mobile` است.
- **ADR-015:** unique روی مدل‌های soft-deletable با partial index و شرط `WHERE deleted_at IS NULL` است و تصمیم هر مدل در task خودش گرفته می‌شود. معیار AUTH-01 به‌روز شد.
- **Git:** قاعده «یک شاخه برای هر milestone» به «یک شاخه برای هر فاز + PR به `master` در پایان فاز» تغییر کرد (CLAUDE.md و WORKFLOW.md). M1.1 و M1.2 روی `feat/m1.1-repo-foundation` مشترک هستند.

### 2026-09-29 — INF-03: سبک pagination
- PRD («دسته‌بندی محصولات» ✓) صراحتاً `page`/`limit` و «تعداد کل» و «اطلاعات صفحه‌بندی» می‌خواهد، پس لیست‌های عمومی هم page/limit شدند (نه cursor). سقف limit برای public ۴۸ و برای admin ۱۰۰ است و page حداکثر ۱۰۰۰.
- **CAT-07:** معیار پذیرش جدید اضافه شد: helper مشترک برای کوئری صفحه‌بندی‌شده (count + offset، مرتب‌سازی قطعی با `id` برای شکستن تساوی) و تست pagination در سطح DB. برآورد از 5h به 6h رسید و کل برآورد از 406h به 407h. به‌جای helper از نوع keyset، helper از نوع offset ثبت شد، چون cursor حذف شده است.
- اصلاح جانبی: مقادیر COMPLETE فاز ۱ و مجموع کل در PLAN.md و ROADMAP.md قدیمی بودند و به‌روز شدند.

### 2026-09-29 — تصمیم‌های کاربر
- همه تصمیم‌های D1 تا D16 به‌جز D13 resolved شدند (ADR-001 تا ADR-013). D13 deferred شد. همه taskهای BLOCKED فاز ۱ تا ۴ به NOT_STARTED منتقل شدند.
- **تغییر نسبت به پیشنهاد قبلی:** validation → 400 و قانون کسب‌وکار → 422 (ADR-011). INF-01 رفتار فعلی repo را تغییر می‌دهد.
- **task جدید:** HANDOFF-01 (آخر فاز ۳، 3h) و OPS-07 (adapter واقعی storage، 3h).
- **جابه‌جایی:** DEC-10 از M2.2 به M5.2 منتقل شد و عنوانش به «Choose real file storage» تغییر کرد. DEC-08 و DEC-09 هم به «Choose real …» تغییر نام دادند.
- **PRD:** شش بخش مرجع طبق D2، D3، D4، D5، D6، D7 و D16 ویرایش شدند (جدول «PRD changes» در DECISIONS.md). taskهای `-00` از این به بعد بخش قالبی خود را بازنویسی و «✓ بازبینی‌شده» می‌کنند.
- **زمان‌بندی:** forecast بر اساس ۱۵ ساعت در هفته اضافه شد.

### 2026-09-29 — مهاجرت به ساختار فازبندی
- ساختار `M0`/`M1` به ۶ فاز، ۲۱ milestone و ۱۳۸ task منتقل شد (اکنون ۱۴۰ task).
- نگاشت فایل‌های قدیمی (محتوا منتقل شد، فایل‌های قدیمی حذف شدند): M0-01 → FND-03، M0-02 → FND-06، M0-03 → FND-07، M1-01 → INF-01، M1-02 → INF-02، M1-03 → INF-03، M1-04 → INF-04، M1-05 → INF-05.
- INF-06 اضافه شد. کارهای قبلی به‌صورت FND-01، FND-02، FND-04 و FND-05 (COMPLETE با شواهد) ثبت شدند.

## Log (جدیدترین بالا)
### 2026-10-06 — AUTH-07 COMPLETE (پایان batch AUTH-06/07)
- `POST /api/v1/auth/refresh`: refresh فقط از cookie خوانده می‌شود، rotation در همان family انجام می‌شود و reuse کل family را revoke می‌کند (audit `auth.refresh_reuse`). کاربر غیرفعال یا حذف‌شده → 401.
- pytest 471 passed؛ ruff، format و mypy سبز.

### 2026-10-06 — AUTH-06 COMPLETE (batch AUTH-06/07)
- `POST /api/v1/auth/verify-otp`، جدول `sessions` (migration `20261006_0004`)، JWT با HS256 ثابت، و refresh در cookie محدود به `/api/v1/auth` (ADR-017).
- pytest 460 passed؛ ruff، format و mypy سبز.

### 2026-10-06 — AUTH-05 COMPLETE (پایان batch AUTH-02/05)
- `POST /api/v1/auth/request-otp`: نرمال‌سازی موبایل، OTP هش‌شده، ابطال کد قبلی، و 429 برای cooldown، هر شماره، هر IP و سقف سراسری (ADR-016).
- pytest 426 passed؛ ruff، format و mypy سبز.

### 2026-10-06 — AUTH-02 COMPLETE
- seed نقش‌ها، permissionها و role_permissions (idempotent و بدون حذف). دیتابیس توسعه seed شد و `warehouse_manager` از آن حذف شد.
- یافته: migration اولیه `warehouse_manager` را insert می‌کند؛ دیتابیس تازه آن را دارد (نیازمند تصمیم کاربر).
- pytest 409 passed؛ ruff، format و mypy سبز.

### 2026-10-06 — AUTH-04 COMPLETE (پایان batch AUTH-01/03/04)
- **انجام شد:** `SmsSender` و `FakeSmsSender` (بدون log کردن کد) ساخته شدند. dependency `get_sms_sender` قابل override است و در production fail-closed می‌شود. `generate_otp_code` کد ۶ رقمی zero-padded یا کد mock را برمی‌گرداند. تست startup production با mock اضافه شد.
- **اعتبارسنجی:** pytest 403 passed؛ ruff، format و mypy سبز.
- **بعدی:** batch بعدی با AUTH-02.

### 2026-10-06 — AUTH-03 COMPLETE
- **انجام شد:** جدول `otp_codes` با migration `20261006_0003`. CHECKهای E.164 و hex-64 روی hash دارد و index روی `(mobile, created_at)`. `hash_otp_code` با HMAC-SHA256 کار می‌کند. setting جدید `OTP_HASH_SECRET` در production اجباری است.
- **اعتبارسنجی:** pytest 393 passed؛ ruff، format و mypy سبز.
- **بعدی:** AUTH-04.

### 2026-10-06 — AUTH-01 COMPLETE
- **انجام شد:** migration `20261006_0002`: فیلدهای `first_name`، `last_name`، `email` و `mobile_verified_at` اضافه شدند؛ `phone` با CHECK فرمت E.164 و partial unique index؛ `normalize_phone()` در `app/core/phone.py`.
- **اعتبارسنجی:** چرخه upgrade/downgrade/upgrade انجام شد؛ pytest 374 passed؛ ruff، format و mypy سبز.
- **بعدی:** AUTH-03.

### 2026-10-06 — SEC-05 COMPLETE
- **انجام شد:** job `secret-scan` در `ci.yml` (gitleaks 8.30.1، sha256 بررسی‌شده، `fetch-depth: 0`، `--exit-code 1`)؛ `.gitleaks.toml` (default rules، allowlist خالی چون هیچ fixture فلگ نشد)؛ بخش Secret scanning در README.
- **اعتبارسنجی:** اسکن کل تاریخچه (24 commit) بدون finding؛ تست منفی محلی: exit 1 (`github-pat`)، شاخه موقت push نشد و حذف شد؛ pytest 345 passed، ruff، format و mypy سبز.
- **بعدی:** AUTH-01.

### 2026-09-30 — فاز ۱ merge شد و فاز ۲ شروع شد
- PR #2 از head قدیمی (`e791371`) merge شده بود. PR #3 دو commit جامانده را وارد کرد: `579bd75` (INF-05) و `56f6e9d`. `master` = `1b5d92e`.
- شاخه `feat/phase-2-core-domain` از `master` ساخته و push شد. SEC-05 اضافه شد.
- **بعدی:** SEC-05.

### 2026-09-29 — INF-05 COMPLETE (فاز ۱ کامل)
- **انجام شد:** `app/shared/audit.py` (`record_audit`، `build_diff`)؛ `"hash"` در `SENSITIVE_KEY_PARTS`؛ `metadata.actor = "system"` برای actor خالی؛ fixtureهای DB به `tests/conftest.py`؛ `tests/test_audit.py` (۱۴ unit + ۲ integration).
- **اعتبارسنجی:** pytest 345 passed و 0 skipped (postgres-test)؛ ruff، format و mypy سبز.
- **بعدی:** PR فاز ۱ به `master` (بازبینی کاربر).

### 2026-09-29 — INF-06 COMPLETE
- **انجام شد:**
  - `app/core/redaction.py`:
    - کلید حساس با substring پیدا می‌شود.
    - `code` فقط اگر ۴ تا ۸ رقم باشد redact می‌شود.
    - Bearer، JWT و موبایل (رقم لاتین، فارسی و عربی) mask می‌شوند.
    - mask موبایل فقط وقتی رقم مجاور باشد انجام نمی‌شود.
  - `JsonFormatter` redaction را روی message، extras، traceback و `str()` آبجکت‌ها اعمال می‌کند و هرگز خطا نمی‌دهد (fallback: `log.redaction_failed`).
  - `tests/test_logging.py` (۴۳ تست، همه روی رشته خروجی نهایی).
- **اعتبارسنجی:** pytest 327 passed و 0 skipped (postgres-test)؛ ruff، format و mypy سبز.
- **بعدی:** INF-05.

### 2026-09-29 — FND-07 COMPLETE
- **انجام شد:** `.github/workflows/ci.yml`: push روی همه شاخه‌ها و PR به `master`؛ `permissions: contents: read`؛ `concurrency`؛ service `postgres:16-alpine` (`project_ak_test`)؛ گام‌های ruff check، ruff format --check، mypy و pytest؛ گام ضد-skip از روی junit XML. actionها pin شده روی `checkout@v4` و `setup-python@v5`.
- **اعتبارسنجی:** محلی: pytest 284 passed و 0 skipped؛ ruff، format و mypy سبز؛ اسکریپت ضد-skip بدون DB با exit 1 fail شد (10 skip). GitHub Actions برای `8c7bf9b` سبز شد.
- **بعدی:** INF-05 یا INF-06.

### 2026-09-29 — FND-06 COMPLETE
- **انجام شد:** سرویس `postgres-test` در `docker-compose.yml` (profile `test`، `127.0.0.1:${TEST_DB_HOST_PORT:-55432}`، بدون volume). `TEST_DB_HOST_PORT` در `.env.example`. guard در `tests/conftest.py`: نام دیتابیس باید با `_test` تمام شود، وگرنه session با exit 3 abort می‌شود. تست‌ها در `tests/test_database_guard.py`. README و CLAUDE.md به‌روز شدند.
- **اعتبارسنجی:** pytest 284 passed بدون skip (روی `postgres-test`)؛ ruff، format و mypy سبز؛ `postgres-test` در سرویس‌های پیش‌فرض compose نیست؛ volume توسعه دست‌نخورده ماند.
- **بعدی:** FND-07 یا INF-05.

### 2026-09-29 — INF-04 COMPLETE
- **انجام شد:** `SoftDeleteMixin` (`deleted_at` با index، `is_deleted`، `soft_delete()` idempotent) و `not_deleted(model)` در `app/db/models/common.py`. `User` به mixin منتقل شد و migration لازم نشد. تست‌ها در `tests/test_soft_delete.py` و `tests/test_database.py`. ADR-015 ثبت شد.
- **اعتبارسنجی:** pytest 272 passed (دیتابیس تست موقت)؛ ruff، format و mypy سبز؛ `compare_metadata` بدون تفاوت.
- **بعدی:** INF-05 یا FND-06.

### 2026-09-29 — INF-03 COMPLETE
- **انجام شد:** `app/shared/pagination.py` شامل `PageParams`، `page_params()` و `public_page_params`/`admin_page_params`، `Page[T]` (`items`، `total`، `page`، `limit`، `pages`)، `resolve_sort` (کلید عمومی ← ordering سمت سرور) و `allowed_query_params`. همچنین `BadRequestError` در `app/core/errors.py`. تست‌ها در `tests/test_pagination.py`.
- **اعتبارسنجی:** pytest 268 passed (دیتابیس تست موقت)؛ ruff، format و mypy سبز.
- **بعدی:** INF-04 یا FND-06.

### 2026-09-29 — INF-01 COMPLETE
- **انجام شد:** `ErrorCode` + `ERROR_STATUS` (منبع واحد code → status)، زیرکلاس‌های 401/403/404/409/422/429 (`Retry-After`)، validation → 400، OpenAPI به‌روز شد، و `tests/test_errors.py` شامل تست 400 برای `Toman`، کامل‌بودن mapping و 500 عمومی. اصلاح‌های جانبی: هدر `X-Request-ID` روی 500، و `disable_existing_loggers=False` در `alembic/env.py`.
- **اعتبارسنجی:** pytest 217 passed (دیتابیس تست موقت)؛ ruff، format و mypy سبز.
- **بعدی:** INF-03.

### 2026-09-29 — INF-02 COMPLETE
- **انجام شد:** `app/shared/money.py` و `tests/test_money.py` (۴۸ تست). تصمیم D18 (ADR-014): modeهای `up`، `down`، `nearest` (half-up)، پیش‌فرض `nearest`/step=1. معیار HTTP 400 به INF-01 منتقل شد.
- **اعتبارسنجی:** pytest کامل با دیتابیس تست موقت؛ ruff، format و mypy سبز.
- **بعدی:** INF-01.

### 2026-09-29 — FND-03 COMPLETE
- **انجام شد:** Dockerfile با pip cache mount و `PIP_INDEX_URL` قابل تنظیم (build arg از `.env`). build با یک تلاش موفق شد. up، migrate، seed و `/health`، `/ready`، `/docs` (200) روی 8001 تأیید شد. هدر گزارش در CLAUDE.md بدون emoji شد. slash commandهای `/next`، `/done`، `/status`، `/blocked` اضافه شدند.
- **اعتبارسنجی:** pytest 24 passed (دیتابیس تست موقت)؛ ruff، format و mypy سبز.
- **بعدی:** INF-02.

### 2026-09-29 — ثبت تصمیم‌ها و ویرایش PRD
- **انجام شد:** DECISIONS.md (ADR-003 تا ADR-013 و جدول PRD changes)، ۲۳ ویرایش در بخش‌های مرجع PRD، به‌روزرسانی PLAN، ROADMAP و taskها، پروتکل جلسه در CLAUDE.md، و یادداشت تاریخی روی نقشه راه قدیمی.
- **بعدی:** FND-03.

### 2026-09-29 — مهاجرت سیستم برنامه‌ریزی
- بازنویسی فایل‌های برنامه‌ریزی؛ ساخت `tasks/phase-01/` (۱۶ فایل) و `tasks/phase-02/` (۱۴ فایل).

### 2026-09-29 — راه‌اندازی سیستم برنامه‌ریزی
- **اعتبارسنجی:**
  - `pytest` با PostgreSQL 16 موقت: 24 passed.
  - ruff، format و mypy: سبز.
  - چرخه alembic downgrade/upgrade: موفق.
  - seed، `docker compose config` و `docker build`: موفق.
  - smoke test با `uvicorn`: `/health` و `/api/v1/ready` پاسخ 200 دادند.
