# DSC-03 — Apply/remove code on cart

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** DSC-02, CART-03 · **Level:** HIGH

## Objective
`POST /cart/discount` و `DELETE /cart/discount`؛ نمایش و محاسبه دوباره کد در `GET /cart`؛ rate limit تلاش‌های ناموفق (D34).

## PRD reference
«کد تخفیف» ✓؛ «سبد خرید» ✓؛ D31، D33، D34 (ADR-039)؛ ADR-040، ADR-041، ADR-042. تصمیم‌های کم‌اثر: ADR-043.

## Plan (batch DSC-02/DSC-03)
- migration `20261018_0020`: جدول `discount_attempts` (id، `cart_id` nullable FK carts CASCADE، `user_id` nullable FK users CASCADE، `ip` INET nullable، `created_at`؛ CHECK حداقل یکی از cart_id/user_id؛ index `(cart_id, created_at)`، `(user_id, created_at)`، `(ip, created_at)`). فقط تلاش ناموفق ثبت می‌شود. این migration در plan تأییدشده DSC-01/ADR-042 پیش‌بینی شده بود.
- `Settings`: `DISCOUNT_ATTEMPT_WINDOW_SECONDS` (900)، `DISCOUNT_MAX_FAILED_PER_OWNER` (10، کاربر یا سبد مهمان)، `DISCOUNT_MAX_FAILED_PER_IP` (30)؛ placeholder در `.env.example`.
- `POST /cart/discount` (200، پاسخ همان `CartResponse`): بدنه `{code}` (`extra="forbid"`، رشته ۱..۶۴؛ نرمال‌سازی با `normalize_code`؛ شکل نامعتبر → 422 `invalid`، نه 400، تا با کد ناموجود فرقی نکند — ولی همچنان تلاش ناموفق شمرده می‌شود). مراحل: lock سبد (مثل CART-02؛ بدون سبد → 404 بدون ساخت) → بررسی rate limit (شمارش تلاش‌های ناموفق در پنجره برای owner و IP؛ ≥ سقف → 429 `RATE_LIMITED` بدون ارزیابی) → خواندن کد زنده با `code` نرمال → `check_code` با subtotal سبد و usage (شمارش redemptionهای زنده؛ برای کاربر با موبایل خودش) → `price_order` با کد؛ `code_applied=False` → `no_eligible_lines`. موفق: `cart.discount_code_id = code.id`، touch سبد، cookie مهمان تمدید. ناموفق: تراکنش rollback، سپس ثبت تلاش در تراکنش جدا، سپس 422.
- `DELETE /cart/discount` (200، `CartResponse`): پاک‌کردن `discount_code_id`؛ idempotent؛ بدون سبد → سبد خالی 200.
- `GET /cart` و `acknowledge-prices`: اگر سبد کد دارد، در هر خواندن دوباره بررسی می‌شود (کد حذف‌شده، غیرفعال، منقضی یا پرشده → اعمال نمی‌شود ولی از سبد پاک نمی‌شود؛ بدون نوشتن در GET). پاسخ فیلد جدید `discount`: `{code, applied: bool, reason: str | null}` یا null؛ `discount_code_amount` و سهم هر خط از calculator. `has_changes` وقتی کد اعمال‌نشده باشد true.
- ادغام سبد (CART-04): کد سبد مهمان اگر سبد کاربر کد ندارد منتقل می‌شود (ADR-040 به‌روز).
- قفل‌ها: lock سبد؛ ردیف کد در این مرحله قفل نمی‌شود (سبد فقط نمایش است؛ شمارش قطعی و FOR UPDATE در ORD-04، D31). کد در شمارش سقف هر کاربر: موبایل نرمال کاربر از جدول users.
- **اصلاحات بازبینی plan (opus؛ جایگزین بندهای بالا هرجا متفاوت‌اند):**
  - ترتیب `POST /cart/discount`: lock سبد (بدون سبد → 404) → `pg_advisory_xact_lock` روی hash IP (شمارش IP سریال؛ owner با lock سبد سریال است) → شمارش تلاش‌های ناموفق در پنجره برای owner (کاربر: `user_id`؛ مهمان: `cart_id`)، IP و سراسری؛ هر کدام ≥ سقف → 429 `RATE_LIMITED` با `Retry-After` (از قدیمی‌ترین تلاش در پنجره)؛ سقف سراسری `DISCOUNT_MAX_FAILED_GLOBAL` با log WARNING (overshoot محدود پذیرفته) → نرمال‌سازی کد در service (شکل بد → `invalid` و شمرده می‌شود) → ارزیابی.
  - شکست: ردیف تلاش در **همان تراکنش** زیر lock درج و commit می‌شود، سپس 422 (الگوی verify_otp)؛ ردیف‌های قدیمی‌تر از پنجره در همان درج پاک می‌شوند (نگهداری). موفقیت هرگز شمارنده را صفر نمی‌کند.
  - شکست روی سبدی که کد دارد کد قبلی را نگه می‌دارد؛ اعمال دوباره همان کد 200 idempotent؛ موفقیت سبد را touch و cookie مهمان را تمدید می‌کند و مبنای قیمت خطوط را عوض نمی‌کند.
  - شمارش استفاده با یک query (`FILTER`) برای کل و برای موبایل کاربر؛ مهمان `user_live=None`. مبنای حداقل سفارش: خطوط قیمت‌گذاری‌شده بعد از تخفیف محصول (ADR-043؛ ORD-04 با خطوط سفارش دوباره بررسی می‌کند).
  - IP: `client_ip` پشت reverse proxy همه را یک IP می‌بیند؛ وابسته به trusted-proxy در OPS-04 (D13). تا آن زمان سقف IP قابل تنظیم است و در ADR-043 و OPS-04 ثبت می‌شود.
  - کد با شکل بد → 422 `invalid` (نه 400) تا همه کدهای بد یک پاسخ داشته باشند؛ فیلد اضافه یا بیش از ۶۴ کاراکتر همچنان 400 (ADR-043). `applied: true` در سبد تضمین نیست؛ شمارش قطعی و FOR UPDATE در ORD-04.
  - ادغام: کد سبد مهمان فقط وقتی سبد کاربر کد ندارد منتقل می‌شود.
  - تست‌های اضافه: 401/403، سقف IP بین سبدهای مختلف و همزمانی در cap-1، کد بد شمرده می‌شود، موفقیت شمارنده را صفر نمی‌کند، Retry-After، درصد گرد به صفر (اعمال‌شده با مبلغ 0)، `no_eligible_lines`، ادغام با دو کد، DELETE بدون سبد، `no-store`، `user_exhausted` بعد از ورود، migration downgrade.
- ریسک‌ها: (۱) brute-force کد (rate limit per owner و IP، پاسخ یکسان invalid؛ تست 429 بعد از سقف و شمارش فقط ناموفق‌ها)؛ (۲) تلاش ناموفق با rollback گم شود (ثبت در تراکنش جدا؛ تست)؛ (۳) مبلغ از کلاینت (فقط `code` پذیرفته؛ فیلدهای دیگر 400)؛ (۴) کد نامعتبرشده بعد از اعمال (بررسی در هر خواندن؛ تست انقضا و حذف)؛ (۵) IP پشت proxy (`client_ip` موجود)؛ (۶) N+1 در GET (یک query کد + یک query شمارش).
- Rollback: `alembic downgrade -1` (فقط dev)؛ `git revert`.

## Acceptance Criteria
- [x] اعمال موفق، همه rejectionها با 422 و `details.type`، و GET با مبالغ calculator (تست).
- [x] rate limit: فقط تلاش‌های ناموفق؛ سقف owner و IP؛ 429 (تست)؛ تلاش ثبت‌شده بعد از rollback باقی است (تست).
- [x] کد بعد از اعمال در هر خواندن دوباره بررسی می‌شود (تست انقضا، حذف، سقف)؛ حذف کد idempotent.
- [x] مهمان و کاربر؛ سقف هر کاربر برای کاربر واردشده؛ ادغام کد در ورود (تست).
- [x] 400/401/403/404/422/429 و `no-store`؛ نقشه پوشش CART-05 به‌روز.
- [x] pytest، ruff، format و mypy سبز.

## Implementation Notes
- کد: `app/modules/cart/discount.py` (`CartDiscountService`)، `app/modules/discounts/repository.py`، `app/modules/cart/view.py` (`price_with_code`، کد در GET)، `schemas.py`، `router.py`، `merge.py`؛ مدل `DiscountAttempt` و migration `20261018_0020`؛ چهار setting جدید. تست: `tests/test_cart_discount.py` (16 تابع تست)؛ نقشه پوشش CART-05 به‌روز.
- **Rollback:** `alembic downgrade -1` (فقط dev)؛ `git revert`.

## Log
- 2026-10-18: plan (batch ۲ جلسه phase؛ بازبین opus).
- 2026-10-18: بازبینی plan (opus): نیازمند تغییر؛ همه موارد must اعمال شد (ثبت تلاش در همان تراکنش زیر lock، advisory lock روی IP، ترتیب lock → limit → نرمال‌سازی، 429 با Retry-After و سقف سراسری، وابستگی IP به OPS-04، کد بد → invalid). بازبینی diff (opus): PASS با should؛ اعمال شد (purge دسته‌ای با SKIP LOCKED، سقف سراسری پیش‌فرض ۱۰٬۰۰۰، Retry-After از تلاشِ آزادکننده، تست سقف سراسری، 429 چیزی ثبت نمی‌کند، تست POST با user_exhausted، assert ورود دوم، `usage_for_user` در repository). pytest (1620)، ruff، format و mypy سبز. COMPLETE.
