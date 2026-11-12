# PROGRESS — منبع واحد «کجاییم؟»

**Last Updated:** 2026-11-11

## Current / Next
- **Phase › Milestone:** 4 Account & admin › M4.2 Admin panel
- **Current Task:** CNT-01 کامل شد. بعدی: CNT-02 (CRUD ادمین سکشن‌ها)، CNT-03 (بنر)، سپس CNT-07 و دروازه فاز ۴.
- **Status:** فازهای ۱ تا ۳ در `master` merge شده‌اند. فاز ۳: PR #6، merge `09da5ac`، git tag `phase-3`، image `ghcr.io/atefekalamati/accessorproject-api:phase-3` (هم‌digest با tag `<sha>`). فاز ۴ شروع شد.
- **Progress:** 120/151 task COMPLETE · وزنی 78.4% (339.5h / 433h) · MVP 100%
- **Blockers:** فاز ۳ مانعی ندارد. در فاز ۵: D8، D9، D10 (انتخاب provider واقعی) و D13.
- **Next Action:** فاز ۴ با `/phase`.
  - ترتیب: M4.1 (CAT-18، ACC-01، ACC-02) → M4.2 (ADM-01، ADM-03، ADM-06؛ ADM-02؛ ADM-08؛ ADM-04، ADM-05؛ ADM-07) → M4.3 (CNT-01..07).
  - دستور کاربر (2026-10-25): plan milestoneها برای تأیید متوقف نمی‌شود؛ فقط استثناهای استاندارد AUTOPILOT متوقف می‌شوند.
  - taskهای وضعیت سفارش و بازپرداخت (ADM-02 و هر task `refund_required`) بازبین opus دارند. یادداشت‌ها: OPS-04 (trusted-proxy) پیش‌شرط production برای سقف IP کد تخفیف و callback پرداخت است (ADR-043). بازبین‌ها همزمان با اجرای کامل suite روی دیتابیس پایه تست pytest اجرا نکنند.
- **Branch:** `feat/phase-4-account-admin` (از `master` در `09da5ac`). شاخه فاز ۳ کاملاً merge شده است.
- **Repo layout:** monorepo از 2026-10-26 (commit `ebcfbd5`).
  - بک‌اند در `BACKEND/` و فرانت در `FRONTEND/` است. CI در `.github/` ریشه است و داخل `BACKEND/` اجرا می‌شود.
  - جلسه بک‌اند از `BACKEND/` باز شود.
  - فایل‌های طراحی و HANDOFF کاربر در ریشه commit نمی‌شوند.
- **Stale branch:** `backend` (local و `origin/backend`، commit `48f1542`) قدیمی است و کاملاً در `master` merge شده (commit اضافه‌ای ندارد). طبق دستور کاربر دست‌نخورده می‌ماند و روی آن کار نمی‌کنیم.

---

## Overall Progress
**78.4%** = 339.5h COMPLETE / 433h planned (estimate). **روش:** وزن‌دهی بر اساس ساعت برآوردی (CANCELLED حذف می‌شود).

## Phase Progress
| Phase | Status | Est. | Complete | % | Deadline (پیش‌بینی) |
|---|---|---|---|---|---|
| 1 Foundation | COMPLETE | 37h | 37h | 100% | 2026-10-09 |
| 2 Core domain | COMPLETE | 142h | 142h | 100% | 2026-12-07 |
| 3 Purchase flow | COMPLETE | 101.5h | 101.5h | 100% | 2027-01-23 |
| 4 Account & admin | IN_PROGRESS | 67h | 59h | 88.1% | 2027-02-24 |
| 5 Release | NOT_STARTED | 43h | 0 | 0% | 2027-03-12 |
| 6 Post-core | NOT_STARTED | 42.5h | 0 | 0% | 2027-04-13 |

## Deadlines & Schedule
- فرض (قابل تغییر): تنها، پاره‌وقت، ۱۵ ساعت در هفته، بدون ددلاین سخت. همه ددلاین‌ها **پیش‌بینی** هستند.
- باقی‌مانده: 93.5h ≈ 6.2 هفته. MVP کامل است.
- **Verdict:** on track نسبت به forecast (بدون buffer).

## Completed Recently
- 2026-11-11: CNT-01 (GET /home: سکشن‌های فعال در بازه به ترتیب display_order؛ carousel با اولویت آیتم دستی و پرکردن از منبع (newest، best_selling، discount، category)، حداکثر ۲۰ با کارت لیست؛ SD rule برای محصول، دسته و صفحه؛ سکشن خالی یا با مقصد غیرعمومی پنهان؛ خطای یک سکشن جداشده؛ چیدمان پیش‌فرض؛ migration 0031).
- 2026-11-11: CNT-06 (فرم تماس: POST /contact برای مهمان و کاربر (201 بدون داده)، سقف دقیق ۵/ساعت IP و ۳/ساعت موبایل با advisory lock و Retry-After، صف ادمین با مجوز جدید contact_messages:manage (support، admin، super_admin)، انتقال new→in_progress→closed، audit بدون متن پیام؛ migration 0030؛ ADR-056).
- 2026-11-10: CNT-05 (پرسش‌های متداول: GET /faq گروه‌بندی‌شده با ترتیب پایدار، فقط منتشرشده، CRUD ادمین با content:manage، رد HTML خام، audit؛ migration 0029).
- 2026-11-10: CNT-04 (صفحه ایستا با Markdown بدون HTML خام: GET /pages/{slug} فقط منتشرشده، CRUD ادمین با content:manage، slug ثابت و 409 تکراری، audit؛ migration 0028).
- 2026-10-27: ADM-07 (ماتریس ۵ نقش × ۵۴ route ادمین با کشف route از OpenAPI؛ تطبیق seed و دیتابیس). M4.2 کامل شد.
- 2026-10-27: ADM-05 (گزارش فروش زمانی روز/هفته شنبه/ماه جلالی به وقت تهران، به تفکیک محصول و دسته از snapshot خطوط؛ بازه ≤ ۳۶۶ روز؛ ADR-055).
- 2026-10-26: ADM-04 (`GET /admin/dashboard`: فروش موفق امروز/۷/۳۰ روز تهران با مبنای `paid_at`، صف‌های کار، هشدار موجودی، مشتری جدید؛ query ثابت؛ ADR-055).
- 2026-10-19: PAY-06 (خرید end-to-end در pytest و stage جدید `purchase` در smoke staging با درگاه fake).
- 2026-10-19: PAY-05 (تست‌های سوءاستفاده و رقابت پرداخت با ترتیب‌های اجباری؛ رفع باگ زمان commit رزرو (D32)).
- 2026-10-19: PAY-04 (job تطبیق پرداخت‌های pending (callback گم‌شده، request_lost، abandoned) زیر advisory lock، purge رویدادها، lifespan با fail-closed در production).
- 2026-10-19: PAY-03 (`POST /payments/callback`: verify سمت سرور، اعمال نتیجه در یک تراکنش با ترتیب ADR-048، refund_required برای mismatch، پرداخت دیرهنگام و پرداخت دوم).
- 2026-10-19: PAY-02 (`POST /payments/init`: شروع، ادامه session معتبر، جایگزینی session منقضی، درگاه بی‌پاسخ، router فقط-dev درگاه fake).
- 2026-10-19: PAY-01 (مدل payment، interface درگاه و fake با state در Postgres؛ migration `0024`؛ ADR-051).
- 2026-10-18: ORD-06 (لغو مشتری `POST /orders/{id}/cancel`، لغو سفارش در انقضای رزرو با job و lazy، مرحله دوم sweep، تست e2e؛ ADR-050).
- 2026-10-18: ORD-04 (`POST /orders`: idempotent، یک تراکنش، رزرو ۱۵ دقیقه، redemption pending، snapshot کامل، یک سفارش pending زنده برای هر کاربر؛ ترتیب سراسری lock در ADR-048).
- 2026-10-18: CAT-17 (sort `best_selling` از واحدهای سفارش‌های paid؛ ADR-047).
- 2026-10-18: ORD-05 (state machine سه وضعیت با guardهای بین فیلدها، history و audit، قفل ردیف سفارش؛ ADR-047).
- 2026-10-18: ORD-03 (`POST /checkout/validate`: quote با ارسال و کد، fingerprint کامل، SD rule، موجودی مؤثر؛ ADR-047).
- 2026-10-18: ORD-02 (زیرساخت Idempotency-Key: per-user، ۲۴ ساعت، replay پاسخ موفق، بدنه متفاوت 422، advisory lock؛ migration `0023`؛ ADR-046).
- 2026-10-18: ORD-01 (schema سفارش، خطوط snapshot، snapshot قیمت و آدرس، تاریخچه وضعیت، شماره `ORD-YYYY-NNNNNN`؛ FK سفارش در رزرو و redemption؛ migration `0022`؛ ADR-046).
- 2026-10-18: ADDR-04 (تست‌های مالکیت و validation آدرس، اثر end-to-end ادمین روی فهرست عمومی و انتخاب روش). M3.3 کامل شد.
- 2026-10-18: ADDR-03 (CRUD ادمین روش ارسال با مجوز جدید `shipping:manage`، audit، قفل ردیف؛ ADR-045).
- 2026-10-18: ADDR-02 (ShippingMethod، محاسبه‌گر هزینه ارسال پشت interface با سقف رایگان روی مبنای بعد از تخفیف‌ها، `GET /shipping-methods`؛ migration `0021`؛ ADR-045).
- 2026-10-18: ADDR-01 (CRUD آدرس‌های خود کاربر، سقف ۱۰ و یک پیش‌فرض زیر lock هر کاربر؛ ADR-045).
- 2026-10-18: DSC-05 (سرویس داخلی redeem/confirm/release با قفل ردیف کد و شمارش زیر lock، outcome بدون raise، تست همزمانی سقف کل و هر موبایل؛ ADR-044). M3.2 کامل شد.
- 2026-10-18: DSC-04 (CRUD ادمین کد تخفیف با `discounts:manage`، audit، شمارش استفاده، فیلتر وضعیت؛ ADR-044).
- 2026-10-18: DSC-03 (POST/DELETE /cart/discount، بررسی دوباره کد در GET، rate limit تلاش‌های ناموفق per owner/IP/سراسری با 429 و Retry-After، انتقال کد در ادغام؛ migration `0020`؛ ADR-043).
- 2026-10-18: DSC-02 (قواعد خالص کد تخفیف با ترتیب rejection قطعی و مبنای حداقل بعد از تخفیف محصول؛ ADR-043).
- 2026-10-18: DSC-01 (جدول‌های discount_codes و discount_redemptions با قیدهای سازگاری، `carts.discount_code_id`، `normalize_code` فقط ASCII؛ migration `0019`؛ ADR-042).
- 2026-10-18: CART-05 (نقشه پوشش خطای ۵ endpoint سبد با guard، تست شکاف‌های 400/401/403، end-to-end مهمان → ورود → سبد). M3.1 کامل شد.
- 2026-10-12: CART-04 (ادغام سبد مهمان در verify-otp، پاک‌شدن cookie، idempotent و امن در همزمانی؛ ADR-040).
- 2026-10-12: CART-03 (GET /cart با قیمت سرور، flag تغییر قیمت per-line با مبنای `seen_*`، POST /cart/acknowledge-prices، flag موجودی بدون عدد؛ migration `0018`؛ ADR-041).
- 2026-10-12: CART-02 (POST/PATCH/DELETE /cart/items برای مهمان و کاربر، موجودی آزاد مؤثر بدون رزرو، 409 بدون عدد موجودی؛ رفع باگ ON CONFLICT با generic plan؛ ADR-040).
- 2026-10-12: CART-01 (carts و cart_items، token مهمان فقط با hash، cookie D30، یک سبد active برای هر کاربر؛ ADR-040).
- 2026-10-12: CART-00، DSC-00، ADDR-00، ORD-00، PAY-00 (نه بخش قالبی PRD بازنویسی و ✓ شد؛ D30–D34، ADR-039).
- 2026-10-12: OPS-09 (CD به GHCR: job publish-image با tag های sha و phase-N، packages:write فقط در همان job).
- 2026-10-12: OPS-08 (staging موقت در CI: image، دیتابیس خالی، migration، seed و smoke؛ project جدای compose).
- 2026-10-12: PRC-06 (suite تجمیعی قیمت: نقشه ۳۲ قاعده → تست با guard، خروجی int، ترتیب بی‌اثر، گردکردن فقط اجزای محاسبه‌شده، tamper API).
- 2026-10-12: INV-09 (تست همزمانی oversell: خریداران موازی، سبدهای متقاطع، ترکیب reserve/commit/release/sweep/اصلاح دستی؛ دفتر movement سازگار).
- 2026-10-12: INV-08 (GET/PATCH /admin/inventory، رزروها و تاریخچه؛ موجودی مؤثر در SQL، وضعیت expired مستقل از job، expected_total؛ ADR-038).
- 2026-10-12: INV-06 (job انقضای رزرو: advisory lock تراکنشی، SKIP LOCKED و lock_timeout، keyset؛ loop در lifespan با `RESERVATION_SWEEP_SECONDS`؛ ADR-036).
- 2026-10-12: INV-05 (commit/release داخلی و idempotent؛ commit منقضی → `EXPIRED` با آزادسازی و 409 `RESERVATION_EXPIRED`؛ اصلاح رقابت re-reserve/commit؛ ADR-036).
- 2026-10-12: INF-07 (pytest-xdist با `-n auto`، یک دیتابیس `<base>_<gwN>_test` برای هر worker؛ suite محلی 5:25 → 2:38).
- 2026-10-12: INV-04 (رزرو: schema، reserve همزمان‌امن و idempotent، انقضای مستقل از job در همه نماها؛ ADR-036).
- 2026-10-12: PRC-03 (PriceHistory با `seq`، تغییر قیمت تنوع و محصول تک‌تنوعی، تاریخچه، history قیمت اولیه؛ ADR-035).
- 2026-10-11: INV-02 (InventoryMovement با CHECKهای سازگاری، اصلاح دستی موجودی با lock و audit؛ ADR-034).
- 2026-10-11: INV-07 (GET /products/{id}/availability؛ وضعیت بدون عدد موجودی، فقط انبار فعال؛ ADR-033).
- 2026-10-11: PRC-05 (GET/PATCH /admin/pricing/settings با `pricing_settings:update`؛ row lock، bump نسخه، audit؛ ADR-033).
- 2026-10-11: PRC-04 (GET /products/{id}/pricing؛ قیمت سرور با `unit_price`، `calculated_at`، SD rule؛ ADR-033).
- 2026-10-11: CAT-12 (نقشه پوشش خطای ۲۲ endpoint کاتالوگ با نگهبان route، 400 برای id نامعتبر، تست end-to-end کاتالوگ). M2.2 کامل شد.
- 2026-10-11: CAT-07 (GET /products و GET /categories/{slug}/products؛ فیلتر، sort و صفحه‌بندی در DB؛ helper `paginate`؛ بازه price در /filters؛ ADR-032).
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
### 2026-11-10 — ترتیب M4.3 (AUTOPILOT)
مقصد `page` در سکشن و بنر به StaticPage نیاز دارد، پس ترتیب M4.3 شد: CNT-04، CNT-05، CNT-06 → CNT-01، CNT-02، CNT-03 → CNT-07. وابستگی CNT-01 به CNT-04 و CNT-03 به CNT-01 در PLAN.md اضافه شد. وضعیت کهنه ADM-04، ADM-05 و ADM-07 در PLAN.md به COMPLETE اصلاح شد.

### 2026-10-26 — نیازمندی‌های فاز ۴ (تصمیم کاربر، ADR-053)
- ACC-00، ADM-00 و CNT-00 تأیید و COMPLETE شدند (D35–D42).
- task جدید ADM-08 (بازپرداخت دستی، HIGH، 3h، opus).
- task جدید CAT-18 (نمونه رنگ hex با migration و `is_new`، طراحی storefront E، 3h، در اولین batch).
- task جدید backlog ACC-05 (حذف حساب با ناشناس‌سازی، 4h، M6.6).
- کل: 151 task، 433h؛ فاز ۴: 67h؛ فاز ۶: 42.5h.
- در فاز ۴ plan milestone برای تأیید متوقف نمی‌شود. taskهای وضعیت سفارش و بازپرداخت (ADM-02، ADM-08) بازبین opus دارند.
### 2026-10-18 — اجرای بقیه فاز ۳ (تصمیم کاربر)
- برای بقیه milestoneهای فاز ۳ plan milestone فرستاده نمی‌شود (نیازمندی‌ها در ADR-039 تأیید شده‌اند). توقف فقط برای planهای PAY-* و استثناهای استاندارد AUTOPILOT. بازبین‌های taskهای کد تخفیف (DSC-*) با model `opus` (پول).
### 2026-10-12 — نیازمندی‌های فاز ۳ (تصمیم کاربر)
- CART-00، DSC-00، ADDR-00، ORD-00، PAY-00 با ۸ تغییر کاربر تأیید شدند (ADR-039). «Done when» این taskها به‌روز شد: CART-01، CART-04، DSC-01، DSC-03، DSC-05، ADDR-02، ORD-02، ORD-03، ORD-04، PAY-03، PAY-04. بدون تغییر برآورد. جمع فاز ۳ در PLAN از 100.5h به 101.5h اصلاح شد (جمع ردیف‌ها؛ PROGRESS از قبل 101.5h بود).
### 2026-10-12 — Phase mode، دروازه فاز، OPS-08/OPS-09 و ترتیب جدید (تصمیم کاربر)
- `/phase` و دروازه فاز (ADR-037). سقف جلسه از ۳ به ۴ batch.
- task جدید در M2.5: OPS-08 (staging موقت و smoke در CI، MEDIUM، 3h) و OPS-09 (CD به GHCR، MEDIUM، 2h). کل: 148 task، 423h؛ فاز ۲: 142h؛ MVP: 280.5h.
- ترتیب: INV-08 + INV-09 + PRC-06 → OPS-08 → OPS-09 → دروازه فاز ۲ → نیازمندی‌های فاز ۳: پیش‌نویس CART-00، DSC-00، ADDR-00، ORD-00 و PAY-00 با هم، بدون ویرایش PRD؛ یک خلاصه (≤۸۰ خط) برای تأیید کاربر؛ بعد از تأیید همه ویرایش‌های PRD در یک commit، سپس `/phase` برای فاز ۳. planهای PAY-* همچنان برای کاربر متوقف می‌شوند.
### 2026-10-12 — task جدید INF-07 (درخواست کاربر)
- INF-07 (LOW، 1.5h، M2.1): کارایی suite تست با pytest-xdist (dependency تأییدشده)، batch جدا قبل از INV-05. کل: 146 task، 418h؛ فاز ۲: 137h؛ MVP: 275.5h.
### 2026-10-12 — D29 و plan رزرو (تصمیم کاربر)
- D29 = گزینه الف (محصول چندتنوعی → 422؛ ADR-035). plan رزرو تأیید شد با قیود: یک رزرو active برای هر سفارش، درستی مستقل از job (رزرو منقضی در availability و commit غیرفعال)، job زیر `pg_try_advisory_lock`، audit هر چهار رخداد. طراحی بازنگری‌شده در `INV-04-reservation-reserve.md`.
### 2026-10-11 — تأیید همه milestoneهای باقی‌مانده فاز ۲ (تصمیم کاربر)
- M2.3 و M2.4 بدون plan جداگانه milestone تأیید شدند. سقف این جلسه ۴ batch. رزرو (INV-04..06): یک plan مشترک برای تأیید کاربر، سپس هر task در یک batch جدا با بازبین subagent. قیود طراحی کاربر (lock مرتب بر اساس variant_id، all-or-nothing، idempotent، 409 RESERVATION_EXPIRED، job انقضا با SKIP LOCKED و actor=system، تست‌های همزمانی) در آن plan رعایت می‌شوند.
### 2026-10-11 — قرارداد ترتیب خطوط قیمت (تصمیم کاربر)
- معیار پذیرش جدید برای CART-03، ORD-03 و ORD-04 (هر CART-*/ORD-* که تابع قیمت را صدا می‌زند): خطوط با ترتیب پایدار (بر اساس id خط) و تست «ورودی به‌هم‌ریخته → خروجی یکسان» (ADR-031). بدون تغییر برآورد.
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
### 2026-11-11 — CNT-01 COMPLETE
GET /home: سکشن‌های فعال در بازه به ترتیب display_order؛ carousel با اولویت آیتم دستی و پرکردن از منبع (newest، best_selling، discount، category)، حداکثر ۲۰ با کارت لیست؛ SD rule برای محصول، دسته و صفحه؛ سکشن خالی یا با مقصد غیرعمومی پنهان؛ خطای یک سکشن جداشده؛ چیدمان پیش‌فرض؛ migration 0031.

### 2026-11-11 — CNT-06 COMPLETE
فرم تماس: POST /contact برای مهمان و کاربر (201 بدون داده)، سقف دقیق ۵/ساعت IP و ۳/ساعت موبایل با advisory lock و Retry-After، صف ادمین با مجوز جدید contact_messages:manage (support، admin، super_admin)، انتقال new→in_progress→closed، audit بدون متن پیام؛ migration 0030؛ ADR-056.

### 2026-11-10 — CNT-05 COMPLETE
پرسش‌های متداول: GET /faq گروه‌بندی‌شده با ترتیب پایدار، فقط منتشرشده، CRUD ادمین با content:manage، رد HTML خام، audit؛ migration 0029.

### 2026-11-10 — CNT-04 COMPLETE
صفحه ایستا با Markdown بدون HTML خام: GET /pages/{slug} فقط منتشرشده، CRUD ادمین با content:manage، slug ثابت و 409 تکراری، audit؛ migration 0028.

### 2026-10-26 — ADM-08 COMPLETE
- ثبت بازپرداخت دستی، migration `0027` و ADR-054:
  - بازگشت `refund_required` روی سفارش لغوشده.
  - مبلغ ادمین وقتی `paid_amount` نامعلوم است.
- بازبین opus برای plan و diff؛ یافته‌ها اعمال شد. pytest 2059 سبز.
- deploy: `python -m app.db.seed`.
- workspace: worktree جدا `E:\BI\ATK-frontend` برای `frontend/phase-1`.
### 2026-10-26 — ADM-02 COMPLETE (batch 4)
- وضعیت ارسال، کد رهگیری و تحویل (order completed)، لغو ادمین (reason `admin`)، migration `0026`.
- بازبین opus برای plan و diff: PASS.
- ADM-08 به خاطر یافته high plan و تصمیم پولی `paid_amount` خالی متوقف شد.
### 2026-10-26 — ADM-06 COMPLETE
- نمایشگر audit فقط برای super_admin.
### 2026-10-26 — ADM-03 COMPLETE
- `/admin/customers` با ماسک موبایل و audit مشاهده (D38).
### 2026-10-26 — ADM-01 COMPLETE
- `/admin/orders` (فیلترها، موبایل ماسک‌شده) و `/admin/payments` (`status`، `failure_reason`).
### 2026-10-26 — ACC-02 COMPLETE؛ M4.1 کامل
- تست IDOR برای همه endpointهای مالکیت‌دار مشتری؛ هیچ نشتی پیدا نشد.
### 2026-10-26 — ACC-01 COMPLETE
- `GET /orders` و `GET /orders/{number}` با payments، history، `can_pay` و `can_cancel`. pytest 2033 سبز.
### 2026-10-26 — CAT-18 COMPLETE؛ monorepo
- نمونه رنگ hex (migration `0025`) و `is_new` در کارت و جزئیات محصول (D42).
- کاربر پروژه را به `BACKEND/` منتقل کرد. `.github` به ریشه رفت و `defaults.run.working-directory: BACKEND` شد. CI سبز شد (`ebcfbd5`).
- `name: atk` در compose ثابت شد تا volume `atk_postgres_data` حفظ شود.
- pytest 2026 سبز.
### 2026-10-25 — دروازه فاز ۳ کامل
- PR #6 توسط کاربر merge شد (`09da5ac`).
- CD (run 40235262109) image را با tagهای `09da5ac…` و `phase-3` و digest یکسان `sha256:8211…fa71` در GHCR منتشر کرد.
- git tag `phase-3` ساخته و push شد.
- شاخه `feat/phase-4-account-admin` ساخته شد.
### 2026-10-25 — HANDOFF-01 COMPLETE؛ فاز ۳ کامل
- PRD با کد هم‌خوان شد: ۵۲ اصلاح در ۱۲ بخش (ADR-052)، با تأیید کاربر.
- `docs/api/openapi.json` و `docs/api/FRONTEND.md` اضافه شدند.
- bug CORS رفع شد: `Idempotency-Key` مجاز و `Retry-After` قابل‌خواندن.
- production بدون `CORS_ORIGINS` صریح بالا نمی‌آید (افزوده کاربر).
- بازبینی opus: PASS WITH CHANGES و یافته‌ها اعمال شد.
- CI: 2013 تست و smoke staging سبز.
### 2026-10-19 — PAY-06 COMPLETE (اجرای مشترک M3.5)
- بازبینی opus: PASS WITH CHANGES و اعمال شد. smoke محلی و pytest 2005 سبز.
### 2026-10-19 — PAY-05 COMPLETE (اجرای مشترک M3.5)
- بازبینی opus: PASS WITH CHANGES؛ یک باگ D32 پیدا و رفع شد. pytest 2002 سبز.
### 2026-10-19 — PAY-04 COMPLETE (اجرای مشترک M3.5)
- بازبینی diff با opus: PASS WITH CHANGES و اعمال شد. pytest 1989 سبز.
### 2026-10-19 — PAY-03 COMPLETE (اجرای مشترک M3.5)
- بازبینی diff با opus: PASS WITH CHANGES و اعمال شد. pytest 1974 سبز.
### 2026-10-19 — PAY-02 COMPLETE (اجرای مشترک M3.5)
- بازبینی diff با opus: PASS WITH CHANGES و اعمال شد. یک flaky زمان‌بندی در تست job انقضا با علت مشخص رفع شد. pytest 1956 سبز.
### 2026-10-19 — PAY-01 COMPLETE (اجرای مشترک M3.5)
- plan مشترک تأیید شد (ADR-051). بازبینی diff با opus: PASS WITH CHANGES و اعمال شد. pytest 1935 سبز.
### 2026-10-18 — ORD-06 COMPLETE (جلسه phase، batch ۱)
- plan بعد از بازبینی opus و تأیید کاربر اجرا شد (لغو با payment pending → 409). بازبینی diff با opus: PASS WITH CHANGES و اعمال شد. قاعده AUTOPILOT در CLAUDE.md به‌روز شد. pytest 1895 سبز.
### 2026-10-18 — ORD-04 COMPLETE (batch ۴ جلسه phase)
- plan با ۴ افزوده کاربر تأیید شد؛ بازبینی plan و diff با opus (یافته deadlock KEY SHARE/FOR UPDATE قبل از پیاده‌سازی رفع شد)؛ pytest 1871 سبز.
### 2026-10-18 — ORD-03، ORD-05 و CAT-17 COMPLETE (batch ۳ جلسه phase)
- بازبینی plan هر سه و diff ORD-03/ORD-05 با opus؛ pytest 1846 سبز.
### 2026-10-18 — ORD-01 و ORD-02 COMPLETE (batch ۲ جلسه phase)
- بازبینی plan و diff با opus؛ pytest 1819 سبز. plan milestone M3.4 در M3.4-PLAN.md.
### 2026-10-18 — ADDR-03 و ADDR-04 COMPLETE (batch ۱ جلسه phase)
- بازبینی plan و diff ADDR-03 با opus؛ pytest 1740 سبز. قوانین جدید کاربر: بازبین read-only (CLAUDE.md)، معیار TRUSTED_PROXIES در OPS-04، توقف plan ORD-04.
### 2026-10-18 — ADDR-01 و ADDR-02 COMPLETE (batch ۴ جلسه phase)
- بازبینی plan و diff ADDR-02 با opus؛ pytest 1705 سبز.
### 2026-10-18 — DSC-04 و DSC-05 COMPLETE (batch ۳ جلسه phase)
- بازبینی plan و diff با opus؛ pytest 1659 سبز. یک اجرای کامل کند (۲:۴۱ ساعت، ۱۲ شکست نامرتبط) به‌خاطر اجرای همزمان pytest بازبین‌ها روی دیتابیس پایه تست بود؛ اجرای تنها سبز.
### 2026-10-18 — DSC-02 و DSC-03 COMPLETE (batch ۲ جلسه phase)
- بازبینی plan و diff با opus؛ pytest 1620 سبز.
### 2026-10-18 — DSC-01 COMPLETE (batch ۱ جلسه phase)
- بازبینی plan و diff با opus؛ pytest 1573 سبز.
### 2026-10-18 — CART-05 COMPLETE (batch ۱ جلسه phase)
- pytest 1573 سبز.
### 2026-10-12 — CART-04 COMPLETE (batch ۴ جلسه phase)
- pytest 1522 سبز.
### 2026-10-12 — CART-03 COMPLETE
- volume `project-ak-staging_postgres_data` وجود ندارد (کاربر و `docker volume ls` تأیید کردند)؛ مورد بسته شد. قاعده مدل بازبین (sonnet پیش‌فرض، opus برای پول/رزرو/پرداخت/auth، retry بدون حذف بازبینی) به CLAUDE.md افزوده شد. pytest 1513 سبز.
### 2026-10-12 — CART-02 COMPLETE (batch ۳ جلسه phase)
- بازبینی plan و diff با subagent؛ pytest 1499 سبز.
### 2026-10-12 — CART-01 COMPLETE (batch ۳ جلسه phase)
- migration `20261012_0017`؛ pytest 1477 سبز.
### 2026-10-12 — نیازمندی‌های فاز ۳ COMPLETE
- خلاصه ≤۸۰ خط، چهار سؤال و ۸ تغییر کاربر؛ PRD، DECISIONS، PLAN در یک commit.
### 2026-10-12 — دروازه فاز ۲ کامل شد
- PR #5 merge شد (`e750ddf`)؛ CI روی `master` سبز؛ image با tagهای `<sha>` و `phase-2` در GHCR (digest یکسان)؛ git tag `phase-2`؛ شاخه `feat/phase-3-purchase-flow`. staging حالا روی tmpfs است (`docker-compose.staging.yml`، درخواست کاربر).
### 2026-10-12 — OPS-09 COMPLETE (batch ۲ جلسه phase)
- job `publish-image`؛ تأیید push در GHCR در گام d دروازه فاز ۲. همه taskهای فاز ۲ COMPLETE.
### 2026-10-12 — OPS-08 COMPLETE (batch ۲ جلسه phase)
- job `staging-smoke` در CI سبز (42s).
### 2026-10-12 — PRC-06 COMPLETE (batch ۱ جلسه phase)
- suite تجمیعی قیمت با نقشه قاعده → تست؛ بدون تغییر کد تولید؛ بازبینی diff با subagent.
### 2026-10-12 — INV-09 COMPLETE (batch ۱ جلسه phase)
- suite همزمانی oversell (۴ تست)؛ بدون تغییر کد تولید؛ بازبینی diff با subagent.
### 2026-10-12 — INV-08 COMPLETE (batch ۱ جلسه phase)
- چهار endpoint ادمین موجودی؛ بازبینی plan و diff با subagent؛ pytest 1452 سبز.
### 2026-10-12 — INV-06 COMPLETE (batch ۳ جلسه)
- job انقضا؛ ۱۹ تست شامل رقابت با commit، release و sweep همزمان. بازبینی plan و diff: APPROVE WITH CHANGES، اعمال شد. CI INV-05 سبز (86s).

### 2026-10-12 — INV-05 COMPLETE (batch ۲ جلسه)
- commit/release با ترتیب lock یکسان؛ ۲۲ تست جدید شامل ۶ رقابت. بازبینی plan: APPROVE WITH CHANGES (اعمال شد، یک race در reserve INV-04 هم بسته شد)؛ diff: APPROVE. CI INF-07 سبز (98s).

### 2026-10-12 — INF-07 COMPLETE (batch ۱ جلسه)
- suite موازی: سریال 324s → 156s محلی (1339 passed). sleep یا انتظار همزمانی وجود نداشت؛ گلوگاه round-trip دیتابیس است.

### 2026-10-12 — INV-04 COMPLETE (batch ۴ جلسه)
- reserve با advisory lock per-order، ترتیب lock یکسان، وضعیت per-item و آزادسازی تنبل؛ ۲۳ مورد تست شامل ۱۰ خریدار همزمان. بازبینی plan و diff: APPROVE WITH CHANGES، اعمال شد. CI PRC-03 سبز.

### 2026-10-12 — PRC-03 COMPLETE (batch ۳ جلسه)
- تغییر قیمت با history و audit؛ ۲۹ تست. بازبینی diff: APPROVE WITH CHANGES، اعمال شد. CI INV-02 سبز.

### 2026-10-11 — INV-02 COMPLETE؛ batch INV-02/PRC-03 متوقف (D29)
- movement و اصلاح دستی موجودی؛ ۱۸ تست. بازبینی plan و diff: APPROVE WITH CHANGES، اعمال شد. PRC-03 به‌خاطر ابهام PRD متوقف شد. plan مشترک رزرو نوشته شد. CI INV-07 سبز.

### 2026-10-11 — INV-07 COMPLETE (پایان batch PRC-04/PRC-05/INV-07)
- وضعیت موجودی عمومی محصول؛ ۹ تست. بازبینی diff: APPROVE. CI PRC-05 سبز.

### 2026-10-11 — PRC-05 COMPLETE (batch PRC-04/PRC-05/INV-07)
- تنظیمات مالیات و گردکردن؛ ۳۰ تست شامل همزمانی و 401/403 قبل از validation. بازبینی diff: APPROVE WITH CHANGES، اعمال شد. CI PRC-04 سبز.

### 2026-10-11 — PRC-04 COMPLETE (batch PRC-04/PRC-05/INV-07)
- `GET /products/{id}/pricing`؛ ADR-033. بازبینی plan (APPROVE WITH CHANGES) و diff (APPROVE) توسط subagent؛ یافته‌ها اعمال شد.

### 2026-10-11 — CAT-12 COMPLETE (پایان batch CAT-07/CAT-12؛ M2.2 کامل)
- `tests/test_catalog_api.py`: نقشه endpoint × کد خطا با نگهبان route و وجود تست؛ ۴۰ تست جدید شامل end-to-end. CI CAT-07 سبز.

### 2026-10-11 — CAT-07 COMPLETE (batch CAT-07/CAT-12)
- لیست عمومی محصولات با قیمت لیست (کمترین final) در SQL و کارت با `unit_price`؛ ۳۰ تست API شامل SD rule، 400/404/422، صفحه‌بندی بدون تکرار و شمارش query. ADR-032.

### 2026-10-11 — CAT-08 COMPLETE (پایان batch PRC-02/CAT-08)
- `GET /products/{slug}` با قیمت PRC-02 و وضعیت موجودی INV-03؛ ۱۳ تست API شامل SD rule و شمارش query. CI PRC-02 سبز.

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
