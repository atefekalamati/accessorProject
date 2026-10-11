# PROGRESS — منبع واحد «کجاییم؟»

**Last Updated:** 2026-10-11

## Current / Next
- **Phase › Milestone:** 2 Core domain › M2.2 Catalog
- **Current Task:** CAT-08 (batch PRC-02/CAT-08). بعدی: CAT-07 + CAT-12.
- **Status:** فاز ۱ کامل است و در `master` merge شد (PR #2 و PR #3؛ `master` = `1b5d92e`). فاز ۲ در جریان است؛ SEC-05 (gitleaks در CI) COMPLETE شد.
- **Progress:** 52/145 task COMPLETE · وزنی 30.3% (126h / 416.5h) · MVP 46.0%
- **Blockers:** فاز ۲ مانعی ندارد. در فاز ۵: D8، D9، D10 (انتخاب provider واقعی) و D13.
- **Next Action:** اتمام CAT-08؛ batch بعدی CAT-07 + CAT-12. سابقه PR فاز ۱: [PR-phase-1.md](PR-phase-1.md).
- **Branch:** `feat/phase-2-core-domain` (از `master` در `1b5d92e`). در پایان فاز ۲ با PR در `master` merge می‌شود. شاخه فاز ۱ (`feat/m1.1-repo-foundation`) کاملاً merge شده است.
- **Stale branch:** `backend` (local و `origin/backend`، commit `48f1542`) قدیمی است و کاملاً در `master` merge شده (commit اضافه‌ای ندارد). طبق دستور کاربر دست‌نخورده می‌ماند و روی آن کار نمی‌کنیم.

---

## Overall Progress
**30.3%** = 126h COMPLETE / 416.5h planned (estimate). **روش:** وزن‌دهی بر اساس ساعت برآوردی (CANCELLED حذف می‌شود).

## Phase Progress
| Phase | Status | Est. | Complete | % | Deadline (پیش‌بینی) |
|---|---|---|---|---|---|
| 1 Foundation | COMPLETE | 37h | 37h | 100% | 2026-10-09 |
| 2 Core domain | IN_PROGRESS | 135.5h | 88.5h | 65.3% | 2026-12-07 |
| 3 Purchase flow | NOT_STARTED | 101.5h | 0.5h | 0.5% | 2027-01-23 |
| 4 Account & admin | NOT_STARTED | 61h | 0 | 0% | 2027-02-20 |
| 5 Release | NOT_STARTED | 43h | 0 | 0% | 2027-03-12 |
| 6 Post-core | NOT_STARTED | 38.5h | 0 | 0% | 2027-03-30 |

## Deadlines & Schedule
- فرض (قابل تغییر): تنها، پاره‌وقت، ۱۵ ساعت در هفته، بدون ددلاین سخت. همه ددلاین‌ها **پیش‌بینی** هستند.
- باقی‌مانده: 290.5h ≈ ۱۹ هفته. MVP باقی‌مانده: 148h ≈ ۱۰ هفته.
- **Verdict:** on track نسبت به forecast (بدون buffer).

## Completed Recently
- 2026-10-10: CAT-05 (media + product_media, FileStorage local/memory, streaming-capped upload, safe re-encode, POST /admin/media, category image_media_id; ADR-028).
- 2026-10-10: PRC-01 (variant price columns + CHECKs, pricing_settings singleton, safe data migration; ADR-027).
- 2026-10-10: CAT-09 (CategoryFilter, public filters from real product data, admin replace + audit; ADR-026).
- 2026-10-10: CAT-10 (admin category CRUD, audit, categories:edit_content, image_url host allowlist, depth ≤ 5; ADR-025).
- 2026-10-10: CAT-06 (public GET /categories tree and /categories/{slug}; hidden ancestor hides subtree; ADR-022).
- 2026-10-10: CAT-04 (VariantOption color/size/model one per key; ProductAttribute one value per key).
- 2026-10-10: CAT-03 (ProductVariant model: global partial-unique SKU, is_active/is_purchasable, no stock or price column).
- 2026-10-10: CAT-02 (Product model: draft/published/archived, published_at CHECK, partial-unique slug, soft delete).
- 2026-10-10: CAT-01 (Category model: tree, partial-unique slug, is_active, display_order, soft delete; ADR-021).
- 2026-10-10: SEC-06 (hashed universal locks via uv; CI and Docker install with --require-hashes; drift check).
- 2026-10-10: SEC-07 (CI runner pinned to ubuntu-24.04; actions/checkout@v7, actions/setup-python@v7).
- 2026-10-09: CAT-00 (PRD «جزئیات محصول» ✓ و «محصولات» ✓ بازنویسی شد؛ public با slug، admin با id؛ ADR-020).
- 2026-10-09: AUTH-12 (consolidated auth security suite; rule → test map for ADR-016/017/018/019).
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
### 2026-10-11 — D28 تأیید شد (تصمیم کاربر)
- مبنای مالیات بعد از تخفیف محصول و سهم کد، ارسال بدون مالیات (سیاست آن D11)، هر جزء یک‌بار گرد و grand_total = جمع اجزا، largest-remainder با tie-break ترتیب خطوط؛ guardها و تست invariant روی ≥۱۰۰۰ سبد تصادفی (ADR-031). PRC-02 از BLOCKED خارج شد.
### 2026-10-11 — PRC-02 مسدود (AUTOPILOT)
- PRD قاعده مبنای مالیات، تقسیم تخفیف کد و مرحله گردکردن را مشخص نمی‌کند؛ موضوع پولی است، پس D28 باز شد و batch ۳ قبل از پیاده‌سازی متوقف شد.
### 2026-10-10 — INV-01 و INV-03 قبل از CAT-11 (AUTOPILOT)
- جزئیات admin محصول (CAT-11) وضعیت موجودی هر تنوع را می‌خواهد، پس batch C/D جابه‌جا شد: batch INV-01/INV-03 (5h)، سپس CAT-11، سپس PRC-02 + CAT-08. تصمیم‌های کم‌اثر در ADR-029.
### 2026-10-10 — AUTOPILOT و plan واحد M2.2 (تصمیم کاربر)
- قواعد AUTOPILOT در CLAUDE.md و [REVIEW-CHECKLIST.md](REVIEW-CHECKLIST.md). plan M2.2 در [M2.2-PLAN.md](M2.2-PLAN.md) یک‌بار فرستاده شد. PRC-01، PRC-02، INV-01 و INV-03 قبل از CAT-11، CAT-08 و CAT-07 می‌آیند. CAT-05 و CAT-11 به Level HIGH رفتند. task جدید CAT-17 (`best_selling`، 1h) در M3.4 ثبت شد. کل: 145 task، 416.5h؛ MVP: 274h.
### 2026-10-10 — تأیید batch CAT-06/CAT-10 (تغییرات کاربر)
- CAT-05 به batch بعد رفت (سقف 8h). کاربر اضافه کرد: allowlist host برای `image_url` (`MEDIA_ALLOWED_HOSTS`) و حداکثر عمق ۵. تصمیم DELETE تأیید شد (ADR-025). CAT-05 باید `image_url` را با `media_id` جایگزین کند.
### 2026-10-10 — تصمیم‌های D26، D27 و Pillow (تصمیم کاربر)
- D26 → ADR-022 (درخت + detail؛ پنهان با هر جد غیرفعال؛ `GET /categories` به PRD اضافه شد). D27 → ADR-023 (`categories:edit_content`)؛ CAT-10 از MEDIUM به HIGH رفت. Pillow برای CAT-05 تأیید شد (ADR-024). venv محلی با lock همگام شد.
### 2026-10-10 — task جدید SEC-07 (درخواست کاربر)
- SEC-07 (LOW، 0.5h، M2.1): pin کردن runner به ubuntu-24.04 و ارتقای checkout/setup-python به v7، قبل از SEC-06. کل: 144 task، 415.5h؛ فاز ۲: 135.5h؛ MVP: 273h.
### 2026-10-09 — تأیید plan CAT-00 (تصمیم کاربر)
- URL عمومی محصول با slug و endpointهای admin با id. CAT-00 بخش «محصولات» (admin) را هم بازنویسی می‌کند؛ برآورد از 2h به 3h رسید و کل برنامه 415h و فاز ۲ 135h شد.
- SEC-06 بیرون از این batch ماند (batch بدون task HIGH). پیش‌نویس PRD در `docs/project/drafts/` و بعد از apply حذف می‌شود.
### 2026-10-09 — بعد از CI سبز batch AUTH-11/12 (تصمیم کاربر)
- ترتیب جدید: batch بعدی CAT-00 + SEC-06. CAT-01 تا CAT-03 فقط بعد از تأیید CAT-00 اجرا می‌شوند.
- `TEST_DATABASE_URL` در CLAUDE.md، README و `.env.example` حالا از `127.0.0.1` استفاده می‌کند، چون `localhost` روی Windows حدود 5 برابر کندتر بود.
- دیتابیس توسعه: `alembic upgrade head` (0004 → `20261009_0005`) و seed اجرا شد. admin حالا 12 permission دارد، از جمله `users:manage`.
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
### 2026-10-11 — PRC-02 COMPLETE (batch PRC-02/CAT-08)
- `app/modules/pricing/calculator.py` (ADR-031). بازبینی plan و diff توسط subagent (هر دو APPROVE WITH CHANGES، اعمال شد). 82 تست واحد شامل ۱۵۰۰ سبد تصادفی با oracle مستقل.

### 2026-10-11 — CAT-11 COMPLETE (batch ۲ جلسه)
- ۱۲ endpoint مدیریت محصول، تنوع و رسانه؛ ADR-030. بازبینی plan و diff توسط subagent (هر دو APPROVE WITH CHANGES، یافته‌ها اعمال شد؛ یک باگ audit رفع شد). CI INV-03 سبز.

### 2026-10-10 — INV-03 COMPLETE (پایان batch INV-01/INV-03)
- `app/modules/inventory/stock.py` (توابع خالص free، max purchasable، وضعیت variant و محصول؛ ADR-029). بازبینی diff توسط subagent (APPROVE WITH CHANGES، اعمال شد). CI INV-01 سبز.

### 2026-10-10 — INV-01 COMPLETE (batch INV-01/INV-03)
- `warehouses` (انبار پیش‌فرض با id ثابت) و `inventory_items` (migration `20261010_0013`)، ADR-029. بازبینی plan و diff توسط subagent (هر دو APPROVE WITH CHANGES، یافته‌ها اعمال شد). pytest 935 passed؛ ruff، format و mypy سبز.

### 2026-10-10 — CAT-05 COMPLETE
- `python-multipart` و `pillow` با lock، migration `20261010_0012`، `POST /admin/media`. بازبینی plan و diff توسط subagent (هر دو APPROVE WITH CHANGES، یافته‌ها اعمال شد). pytest 881 passed؛ ruff، format و mypy سبز. CI PRC-01 سبز. `.env` محلی: `MEDIA_ALLOWED_HOSTS` و `MEDIA_PUBLIC_BASE_URL` (dev) اضافه شد.

### 2026-10-10 — PRC-01 COMPLETE (پایان batch CAT-09/PRC-01)
- migration `20261010_0011`. بازبینی plan و diff توسط subagent مستقل (هر دو APPROVE WITH CHANGES، یافته‌ها اعمال شد). pytest 822 passed؛ ruff، format و mypy سبز. CI CAT-09 سبز.

### 2026-10-10 — CAT-09 COMPLETE
- `category_filters` (migration `20261010_0010`)، `GET /categories/{slug}/filters`، `PATCH /admin/categories/{id}/filters`. pytest 790 passed؛ ruff، format و mypy سبز. CI CAT-10 سبز. CAT-05 متوقف شد: `python-multipart` یک dependency جدید است (استثنای AUTOPILOT).

### 2026-10-10 — CAT-10 COMPLETE (پایان batch CAT-06/CAT-10)
- `/admin/categories` (GET/POST/PATCH/DELETE)، مجوز `categories:edit_content`، `MEDIA_ALLOWED_HOSTS`، عمق ۵، advisory lock برای چرخه همزمان. pytest 767 passed؛ ruff، format و mypy سبز. CI CAT-06 سبز.

### 2026-10-10 — CAT-06 COMPLETE (batch CAT-06/CAT-10)
- `GET /categories` و `GET /categories/{slug}` با recursive CTE. pytest 693 passed؛ ruff، format و mypy سبز. CI CAT-04 سبز.

### 2026-10-10 — CAT-04 COMPLETE (batch ۲)
- مدل‌های `ProductAttribute` و `VariantOption` و migration `20261010_0009`. pytest 681 passed؛ ruff، format و mypy سبز. CI CAT-03 سبز.

### 2026-10-10 — CAT-03 COMPLETE (پایان batch SEC-07/SEC-06/CAT-01..03)
- مدل `ProductVariant` و migration `20261010_0008`. pytest 667 passed؛ ruff، format و mypy سبز. CI CAT-02 سبز.

### 2026-10-10 — CAT-02 COMPLETE
- مدل `Product` و migration `20261010_0007`؛ ADR-021 تکمیل شد. pytest 654 passed؛ ruff، format و mypy سبز. CI CAT-01 سبز.

### 2026-10-10 — CAT-01 COMPLETE
- مدل `Category` و migration `20261010_0006`؛ ADR-021 (D25). pytest 637 passed؛ ruff، format و mypy سبز. CI SEC-06 سبز.

### 2026-10-10 — SEC-06 COMPLETE
- `requirements.lock` و `requirements-dev.lock` با hash (uv، universal)، `scripts/lock.py`، نصب CI و Docker با `--require-hashes` و drift check. pytest 623 passed در venv نصب‌شده از lock؛ docker build سبز.

### 2026-10-10 — SEC-07 COMPLETE (batch SEC-07/SEC-06/CAT-01..03)
- `runs-on: ubuntu-24.04`، checkout و setup-python روی v7 (تأیید وجود release). pytest 623 passed؛ ruff و mypy سبز.

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
