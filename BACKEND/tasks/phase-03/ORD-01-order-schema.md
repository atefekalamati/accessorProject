# ORD-01 — Order, OrderItem snapshot, OrderPriceSnapshot, address snapshot

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 5h (estimate) · **Deadline:** — · **Dependencies:** ORD-00, PRC-01 · **Level:** HIGH

## Objective
schema سفارش که بعد از ثبت تغییرناپذیر است و از تغییر محصول، قیمت، آدرس، کد یا روش ارسال اثر نمی‌گیرد. هیچ endpointی در این task نیست (ORD-04 می‌سازد).

## PRD reference
«نتیجه سفارش» ✓ (مدل داده)؛ «قیمت و مالیات» ✓ (نگاشت OrderItem در ADR-031)؛ ADR-036 (FK رزرو)، ADR-044 (FK redemption)، ADR-045 (snapshot روش ارسال)، M3.4-PLAN.

## Plan (batch ORD-01/ORD-02)
- `app/db/models/orders.py` (enumها `OrderStatus`، `PaymentStatus`، `ShipmentStatus`، `CancelReason`، `StatusField`):
  - `orders` (Timestamp): `order_number` (unique، CHECK `^ORD-[0-9]{4}-[0-9]{6,}$`)، `user_id` FK users RESTRICT، `phone` (E.164 موبایل تأییدشده؛ CHECK)، `status` (`pending_payment|confirmed|completed|cancelled`)، `payment_status` (`unpaid|pending|paid|failed|refund_required`)، `shipment_status` (`not_shipped|preparing|shipped|delivered`)، `cancel_reason` (`customer|expired|admin`؛ CHECK: cancelled ⇔ reason)، مبالغ BIGINT `subtotal`، `product_discount_total`، `discount_code_amount`، `tax_amount`، `shipping_amount`، `grand_total` (CHECK همه ≥ 0 — BIGINT سقف است و calculator خروجی را در BIGINT نگه می‌دارد — و `grand_total = subtotal − product_discount_total − discount_code_amount + tax_amount + shipping_amount`)، `currency` (CHECK `'TOMAN'`)، `discount_code_id` FK RESTRICT nullable + `discount_code` متن snapshot (هر دو یا هیچ)، `shipping_method_id` FK RESTRICT + `shipping_method_title` snapshot. index روی `(user_id, created_at)` و `status`.
  - شماره سفارش: sequence `order_number_seq` و تابع خالص `format_order_number(year, n)` → `ORD-2026-000123` (حداقل ۶ رقم؛ gap مجاز). سال از `utc_now()`.
  - `order_items`: `order_id` FK RESTRICT، `position` (ترتیب پایدار خطوط، unique با order)، `product_id`/`variant_id` FK RESTRICT (variant ارجاع‌شده فقط soft delete)، snapshot `product_title`، `sku`، `variant_label` (گزینه‌ها مثل `color: Red / size: M`)، `quantity` (`1..MAX_STOCK_QUANTITY`)، `unit_price` (original)، `unit_final_price`، `subtotal`، `product_discount`، `code_discount`، `discount_amount` (= جمع دو تخفیف)، `tax_amount`، `final_line_total`؛ CHECKها: `discount_amount = product_discount + code_discount`، `final_line_total = subtotal − discount_amount + tax_amount`، `subtotal = unit_price × quantity`، همه ≥ 0.
  - `order_price_snapshots` (یک‌به‌یک، PK = `order_id`): `pricing_version`، `tax_enabled`، `tax_rate_bps`، `rounding_mode`، `rounding_step`، `fingerprint` (۶۴ hex)، `calculated_at`، `shipping_free_threshold` (nullable، مبنای تصمیم ارسال)، `code_applied`.
  - `order_addresses` (یک‌به‌یک، PK = `order_id`): کپی فیلدهای Address (بدون FK به addresses؛ حذف سخت آدرس سفارش را عوض نمی‌کند) + `source_address_id` nullable.
  - `order_status_history` (CreatedAt): `order_id`، `field` (`order|payment|shipment`)، `old_status` nullable، `new_status`، `actor_user_id` FK SET NULL nullable (null = system)، `reason` nullable ≤۵۰۰. ORD-05 از آن استفاده می‌کند.
  - FK جدید `order_id → orders` (RESTRICT) روی `inventory_reservations` و `discount_redemptions` (هر دو در docstring مدل برای ORD-01 وعده داده شده‌اند).
- migration `20261018_0022` (literalها کپی، ADR-021)؛ ثبت در `__init__`، `_MODELS`، `EXPECTED_TABLES`، `HEAD_REVISION`.
- تست‌ها: fixture `make_order` در conftest (سفارش حداقلی با کاربر جدا؛ teardown اول redemptionها، movementها/آیتم‌ها/رزروهای سفارش و سپس history/آیتم/snapshot/آدرس/سفارش را حذف می‌کند). بازنویسی `order_id=uuid4()` در تست‌های رزرو، redemption، مدل تخفیف و oversell به `make_order`. `tests/test_order_models.py`: CHECKهای وضعیت، cancel_reason، جمع مبالغ، الگوی شماره، unique شماره و position، FKهای RESTRICT (حذف variant/کد/روش ارجاع‌شده رد می‌شود؛ رزرو/redemption با order_id ناموجود رد می‌شود)، snapshot بعد از تغییر محصول/قیمت/آدرس ثابت می‌ماند، `format_order_number` (unit؛ شبیه موبایل نیست).
- **ریسک‌ها:** (۱) snapshot ناقص → تست تغییر منبع؛ (۲) ناسازگاری مبالغ → CHECK DB + تست؛ (۳) FK جدید تست‌های موجود را می‌شکند → fixture مشترک و اجرای کامل suite؛ داده موجود dev/staging با order_id یتیم → migration قبل از افزودن FK ردیف‌های یتیم را گزارش و اگر وجود داشت با خطای روشن متوقف می‌شود (staging tmpfs است)؛ (۴) شماره شبیه موبایل → CHECK؛ (۵) پول float → فقط BIGINT.
- **اصلاحات بازبینی plan (opus):**
  - CHECKهای خط: `product_discount = (unit_price − unit_final_price) × quantity`، `unit_final_price ≤ unit_price`، `subtotal − discount_amount ≥ 0`؛ ضرب و جمع در CHECK با `::numeric` (overflow میانی BIGINT).
  - `orders`: `discount_code_id IS NULL ⇒ discount_code_amount = 0`؛ سال شماره سفارش = سال UTC `created_at` (ORD-04 هر دو را از یک `now` می‌سازد). جمع سرآیند = Σ خطوط با CHECK ممکن نیست → ORD-04 در service assert و تست می‌کند.
  - indexها: `order_items(variant_id)`، `order_items(product_id)`، `order_status_history(order_id, created_at)`؛ FK مرکب `(variant_id, product_id)` مانند cart_items.
  - `fingerprint` ذخیره‌شده = fingerprint quote در ORD-03 (کد و ارسال را می‌پوشاند، D34)، نه fingerprint calculator.
  - snapshot: `code_applied` حذف؛ `shipping_method_cost` (هزینه روش قبل از سقف رایگان) اضافه.
  - Shipment جدا و کد رهگیری به ADM (فاز ۴) موکول؛ وضعیت ارسال، روش و هزینه روی `orders` (ADR-046).
  - fallout FK گسترده‌تر: علاوه بر فایل‌های بالا `test_admin_inventory.py`، `test_cart_items.py`، `test_cart_discount.py`، `test_admin_discounts.py`. `make_order` صریحاً به `make_account`، `catalog` و fixture روش ارسال وابسته است تا اول teardown شود (LIFO) و روش ارسال خودش را می‌سازد و حذف می‌کند.
  - sequence سراسری است و سالانه reset نمی‌شود؛ سال میلادی UTC. migration ردیف یتیم را هرگز حذف نمی‌کند و با خطای روشن متوقف می‌شود.
  - یادداشت DECISIONS: حذف حساب در فاز ۴ با `orders.user_id RESTRICT` به ناشناس‌سازی کاربر نیاز دارد.
- **Rollback:** `alembic downgrade -1` (فقط dev/test؛ هنوز داده واقعی نیست)؛ `git revert`.

## Acceptance Criteria
- [x] past orders immune to product changes (تست).
- [x] order number format `ORD-YYYY-NNNNNN` که شبیه موبایل نیست (CHECK + تست).
- [x] مدل‌ها، migration، drift و ثبت‌ها؛ FKهای رزرو و redemption.
- [x] pytest، ruff، format و mypy سبز.

## Implementation Notes
- کد: `app/db/models/orders.py`، migration `20261018_0022`، FK در `inventory.py` و `discounts.py`. تست: `tests/test_order_models.py`؛ fixture `make_order`/`order_factory`/`new_order` در `tests/conftest.py` و بازنویسی order_idهای تصادفی در ۹ فایل تست.
- **Rollback:** `alembic downgrade -1` (فقط dev/test)؛ `git revert`.

## Log
- 2026-10-18: plan (batch ۲ جلسه phase؛ بازبین opus چون مبالغ پولی ذخیره می‌شوند).
- 2026-10-18: بازبینی plan (opus): APPROVE WITH CHANGES؛ همه ۹ مورد و پیشنهادها اعمال شد (بخش «اصلاحات بازبینی plan»).
- 2026-10-18: بازبینی diff (opus): PASS WITH CHANGES؛ اعمال شد (ثبت مدل‌ها در `alembic/env.py`، کامنت قدیمی FK، docstring ترتیب teardown، guard در CHECK سال، تست FK redemption، ترتیب `__all__`). pytest (1792)، ruff، format و mypy سبز. COMPLETE.
