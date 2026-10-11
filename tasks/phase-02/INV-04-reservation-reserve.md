# INV-04 — Reservation models + reserve service

**Status:** NOT_STARTED (plan منتظر تأیید کاربر) · **Priority:** HIGH · **Estimate:** 5h (estimate) · **Deadline:** — · **Dependencies:** INV-02, INV-03, ADR-007 · **Level:** HIGH

## Combined plan INV-04 / INV-05 / INV-06 (یک plan، سه batch جدا، هر کدام با بازبین subagent)

### قیود کاربر (2026-10-11)
رزرو در `POST /orders` (ADR-007، D6)، TTL ۱۵ دقیقه؛ `free = total − active reservations`؛ lock آیتم‌ها `FOR UPDATE` به ترتیب `variant_id`؛ all-or-nothing برای هر سفارش؛ reserve/commit/release idempotent؛ commit فقط اگر active و منقضی‌نشده، وگرنه 409 `RESERVATION_EXPIRED`؛ commit دوباره = no-op؛ job انقضا: batch، `SKIP LOCKED`، audit با actor=system؛ تست‌ها: N خریدار همزمان برای آخرین واحد → دقیقاً ۱ موفق؛ رقابت commit با انقضا؛ هرگز موجودی منفی.

### Schema (migration `20261011_00NN`، در INV-04)
- `inventory_reservations`: `id`، `order_id` (UUID nullable، **بدون FK تا ORD-01** که جدول orders را می‌سازد و FK را اضافه می‌کند)، `cart_id` (nullable، بدون FK)، `user_id` (FK users، SET NULL)، `status` (CHECK: active، released، committed، expired)، `expires_at`، `committed_at`، `released_at`، timestamps. partial unique `(order_id) WHERE status = 'active'`؛ index `(status, expires_at)`. CHECK: committed ⇔ `committed_at`؛ released/expired ⇔ `released_at`.
- `inventory_reservation_items`: `reservation_id` (FK RESTRICT)، `inventory_item_id` (FK RESTRICT)، `product_id`، `variant_id`، `quantity` (`1..MAX_STOCK_QUANTITY`)؛ unique `(reservation_id, inventory_item_id)`.
- invariant (ADR-029): `inventory_items.reserved_quantity == SUM(quantity)` آیتم‌های رزروهای `active`. هر تست رزرو آن را بعد از اجرا بررسی می‌کند (helper مشترک).

### INV-04 — reserve (5h)
- `ReservationService.reserve(order_id, user_id, lines, now)`؛ داخلی (endpoint عمومی ندارد)، در تراکنش فراخواننده (ORD-04) یا تراکنش خودش.
- lineها: تکراری‌ها ادغام، `quantity` int strict `1..MAX`؛ مرتب بر اساس `variant_id`.
- idempotency: اگر رزرو active برای `order_id` هست → همان برگردانده می‌شود (lineهای متفاوت → 409 `CONFLICT`).
- ترتیب lock (ADR-034): variantها `FOR SHARE` به ترتیب `variant_id` (فعال، قابل خرید، حذف‌نشده؛ وگرنه 422) → InventoryItemهای انبار پیش‌فرض `FOR UPDATE` با `ORDER BY variant_id, warehouse_id`.
- آزادسازی تنبل (ADR-029): زیر همان lock، رزروهای active منقضی‌شده‌ای که روی همین آیتم‌ها هستند با `FOR UPDATE SKIP LOCKED` گرفته و expired می‌شوند (بدون انتظار، پس deadlock با commit که اول reservation و بعد item را قفل می‌کند پیش نمی‌آید). رزروی که قفلش گرفته نشد تا sweep بعدی موجودی را نگه می‌دارد (جهت محافظه‌کارانه).
- all-or-nothing: اگر برای هر line `free < quantity` → 409 `INSUFFICIENT_STOCK` با `details` شامل variant_idها و rollback کامل. وگرنه `reserved += q` برای هر آیتم، movement `reserve` (reference reservation)، رزرو با `expires_at = now + 15m`، audit `reservation.created`.
- تست‌ها: ۱۰ خریدار همزمان برای آخرین واحد (sessionهای جدا، `asyncio.gather`) → دقیقاً ۱ موفق و ۹ تا 409؛ دو سفارش چندتنوعی با ترتیب معکوس lineها همزمان → بدون deadlock؛ idempotency (دو reserve با یک order_id → یک رزرو)؛ all-or-nothing (یک line ناکافی → هیچ آیتمی تغییر نمی‌کند)؛ رزرو منقضی آزادسازی تنبل؛ variant غیرفعال/حذف‌شده → 422؛ invariant.

### INV-05 — commit / release (3h)
- هر دو: اول reservation `FOR UPDATE`، سپس آیتم‌ها `FOR UPDATE` به ترتیب `variant_id` (همان ترتیب job).
- `commit(reservation_id, now)`: committed → no-op (همان نتیجه)؛ released/expired → 409 `RESERVATION_EXPIRED`؛ active و `now ≥ expires_at` → در همان تراکنش expired و آزاد می‌شود، commit می‌شود و سپس 409 `RESERVATION_EXPIRED` برمی‌گردد (نتیجه به‌صورت مقدار برگشتی، نه exception داخل تراکنش، تا آزادسازی rollback نشود)؛ active و معتبر → `total −= q` و `reserved −= q` در یک UPDATE برای هر آیتم، movement `commit`، status committed، audit `reservation.committed`.
- `release(reservation_id, reason)`: active → released، `reserved −= q`، movement `release`، audit؛ released/expired → no-op؛ committed → 409 `RESERVATION_ALREADY_CONSUMED`.
- تست‌ها: commit دوباره no-op (بدون movement دوم)؛ commit بعد از انقضا 409 و موجودی آزاد شده؛ release دوباره no-op؛ release بعد از commit → 409؛ رقابت commit با release (فقط یکی اثر دارد)؛ invariant و total ≥ 0.

### INV-06 — expiry job (3h)
- `release_expired(batch_size=100, now)`: `SELECT … WHERE status='active' AND expires_at <= now ORDER BY expires_at, id LIMIT n FOR UPDATE SKIP LOCKED`؛ برای هر رزرو آیتم‌ها به ترتیب `variant_id` قفل، status expired، `reserved −= q`، movement `release` (reason `expired`)، audit `reservation.expired` با actor=system. تکرار تا batch خالی شود (سقف تعداد دور).
- اجرا: یک loop در lifespan برنامه هر `RESERVATION_SWEEP_SECONDS` ثانیه (setting جدید، پیش‌فرض 60، صفر = خاموش؛ در تست‌ها خاموش) + اجرای دستی `python -m app.modules.inventory.jobs`. بدون dependency جدید. چند instance همزمان امن است (SKIP LOCKED).
- تست‌ها: رزروهای منقضی آزاد و expired می‌شوند و فعال‌ها دست نمی‌خورند؛ رقابت commit با job: یا commit موفق و job آن را رد می‌کند، یا job expire می‌کند و commit 409 می‌گیرد، هرگز هر دو؛ دو job همزمان یک رزرو را دو بار آزاد نمی‌کنند؛ audit با `actor: system`؛ invariant.

### ریسک‌ها و rollback (هر سه)
- ریسک‌ها: oversell (lock + CHECK `reserved ≤ total` backstop + تست همزمانی)؛ deadlock (یک ترتیب lock، SKIP LOCKED در مسیر عکس)؛ رزرو منقضی مصرف‌شده (بررسی `expires_at` زیر lock در commit)؛ drift شمارنده (تست invariant)؛ ساعت (همه با `utc_now()` سرور، `now` تزریق‌پذیر برای تست مرز).
- Rollback: migration جدید `downgrade -1` (فقط dev)؛ `git revert`. job با `RESERVATION_SWEEP_SECONDS=0` خاموش می‌شود.

### سؤال‌های باز برای تأیید
1. idempotency بر اساس `order_id` با unique فقط روی رزروهای active (تا retry پرداخت بعد از انقضا بتواند رزرو تازه بگیرد؛ PAY-04). موافقید؟
2. اجرای job داخل process برنامه (lifespan loop) به‌جای cron جدا. موافقید؟
3. audit برای هر چهار رخداد (created، committed، released، expired) علاوه بر movement. موافقید؟

## Log
- 2026-10-11: plan مشترک INV-04..06 نوشته شد؛ منتظر تأیید کاربر.
