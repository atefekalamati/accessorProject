# ORD-06 — لغو مشتری، لغو سفارش با انقضای رزرو، تست‌های سفارش

**Status:** IN_PROGRESS · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** ORD-03, ORD-04, ORD-05, INV-06 · **Level:** HIGH

## Objective
لغو سفارش `pending_payment` توسط مشتری، و لغو سفارش وقتی رزرو آن منقضی می‌شود (job یا بررسی lazy). هر دو در یک تراکنش و با ترتیب lock ADR-048 رزرو و redemption را آزاد می‌کنند. تست‌های باقی‌مانده سفارش، به‌علاوه یک تست end-to-end از سبد تا سفارش و لغو.

## PRD reference
«نتیجه سفارش» ✓ (`POST /orders/{id}/cancel`؛ «لغو توسط مشتری فقط در `pending_payment`؛ رزرو و redemption آزاد می‌شوند»؛ «انقضای رزرو (job یا اولین بررسی): سفارش `cancelled` با reason `expired`، redemption آزاد، audit با actor system (D34)»)؛ «موجودی و رزرو» ✓؛ ADR-036، ADR-046، ADR-047، ADR-048، ADR-049.

## Scope
- داخل: `POST /api/v1/orders/{id}/cancel`؛ لغو سفارش در job انقضا (`app/modules/inventory/jobs.py`، ADR-047)؛ انقضای lazy هنگام لغو؛ تست‌ها.
- خارج: `GET /orders` و `GET /orders/{orderNumber}` طبق PLAN.md در **ACC-01** می‌مانند (یادداشت PROGRESS اصلاح شد). لغو ادمین (ADM، فاز ۴). مسیر پرداخت (PAY-02..04).

## Plan
1. **منطق مشترک** در `app/modules/orders/cancel.py` (`OrderCancellation`؛ در تراکنش فراخواننده، بدون commit). docstring: ردیف سفارش با `FOR UPDATE` کامل قفل می‌شود، نه `NO KEY UPDATE`، چون `transition()` دوباره `FOR UPDATE` می‌گیرد و ارتقای lock بعد از lock inventory خطرناک است.
   - `cancel_locked(order, *, actor_user_id, request)` برای ردیفی که فراخواننده قفل کرده است:
     1. **اول بررسی وضعیت، بدون هیچ اثر جانبی:** `check_transition(state_of(order), ORDER, CANCELLED)`. اگر نامعتبر بود → 422 `INVALID_STATE_TRANSITION`. 409 `RESERVATION_ALREADY_CONSUMED` فقط برای حالت دفاعی «`pending_payment` با رزرو committed» است.
     2. رزرو active سفارش: اول `ReservationService.expire(id, skip_locked=False, now=None)`. این تابع lockها را می‌گیرد و `now` را بعد از آن‌ها می‌خواند. اگر True برگرداند → reason `expired` و actor system. اگر False برگرداند و رزرو هنوز active است → `release(reason="cancelled by customer", now=None)` با reason `customer`. lock دوم در همان تراکنش هزینه‌ای ندارد.
     3. اگر رزرو active وجود ندارد: آخرین رزرو سفارش `expired` است، یا `expires_at ≤ now` → reason `expired` و actor system. وگرنه `customer`.
     4. `RedemptionService.release(order_id)`. نتیجه آن (`released`/`already_released`/`none`) در `after` همان audit `order.status_changed` (کلید `redemption`) و در log INFO فقط با id ثبت می‌شود.
     5. `OrderStateService.transition(order → cancelled, cancel_reason, actor, reason)` که history و audit را می‌نویسد.
   - ترتیب lock (ADR-048): advisory سفارش → ردیف سفارش `FOR UPDATE` → inventory → ردیف رزرو → redemption. `_order_key` در `reservation.py` با نام `order_lock_key` عمومی می‌شود تا کلید یک منبع داشته باشد.
2. **`ReservationService.expire`** پارامتر keyword `skip_locked: bool = True` می‌گیرد. رفتار job تغییر نمی‌کند. در لغو lazy منتظر می‌ماند، چون ردیف سفارش از قبل قفل شده است. بقیه `reservation.py` تغییر نمی‌کند.
3. **`POST /api/v1/orders/{id}/cancel`** (router → `OrderService.cancel`):
   - `get_current_user` (401، قبل از 400 مسیر) → `id: UUID` (400) → `allowed_query_params()` (400). بدنه ندارد.
   - مالکیت قبل از advisory: `SELECT id WHERE id AND user_id`. اگر پیدا نشد → 404 `NOT_FOUND`. بعد advisory → `FOR UPDATE` دوباره با فیلتر `user_id`.
   - اگر از قبل `cancelled` باشد → 200 با وضعیت فعلی و `cancel_reason` ذخیره‌شده (ممکن است `expired` باشد)، بدون نوشتن و بدون audit.
   - **وضعیت پرداخت (سؤال از کاربر، ثبت در ADR-050):** پیشنهاد این است که لغو با `unpaid` و `failed` مجاز باشد و با `pending` (مشتری در درگاه است) → 409 `PAYMENT_IN_PROGRESS`. با این کار لغو مشتری هرگز به `refund_required` نمی‌رسد. pending گیرکرده را reconciliation (PAY-04) و انقضای رزرو حل می‌کنند. انقضا همیشه لغو می‌کند (D32).
   - پاسخ 200 `OrderStatusResponse {id, order_number, status, payment_status, shipment_status, cancel_reason, updated_at}` با `Cache-Control: no-store`. نمای کامل سفارش در ACC-01 می‌آید.
   - بدون Idempotency-Key: لغو ذاتاً idempotent است.
4. **job انقضا** (`_expire_one`):
   - `order_id` رزرو (تغییرناپذیر) قبل از lockها خوانده می‌شود. رزرو بدون سفارش مثل قبل پردازش می‌شود.
   - رزرو با سفارش، در همان تراکنش هر رزرو: `pg_try_advisory_xact_lock` (اگر نگرفت → skip) → ردیف سفارش `FOR UPDATE SKIP LOCKED` (اگر نگرفت → skip) → `expire()` (اگر False → skip، چیزی نوشته نمی‌شود) → اگر سفارش `pending_payment` است → `cancel_locked` با actor `None`.
   - سفارش در وضعیت دیگری با رزرو active: فقط expire و log WARNING بدون PII.
   - **مرحله دوم sweep:** سفارش‌های `pending_payment` که رزرو active و منقضی‌نشده ندارند (یعنی رزروشان قبل از ORD-06 یا در deploy غلتان با job قدیمی بسته شده) با همان lockها و keyset paging لغو (`expired`) می‌شوند.
   - `SweepResult` شمارنده جدید `cancelled` می‌گیرد.
5. **مستندات:** ADR-050 (معنای لغو، انقضای lazy، invariant «هر مسیری که رزرو سفارش را بدون commit می‌بندد، سفارش را در همان تراکنش لغو می‌کند»، مسیرهای lazy: فعلاً لغو، بعداً PAY-02/03 و ACC-01). docstringهای `jobs.py`، `state_service.py` و `cancel.py`. PLAN.md: ردیف ORD-06 scope جدید را می‌گیرد و «expiry cancels the order» از PAY-04 حذف می‌شود.
- بدون migration و بدون تغییر schema. `CancelReason` از قبل `customer`/`expired` دارد.

## Risks
1. **deadlock** بین لغو، job، ORD-04 و PAY-03 آینده: همه مسیرهای سفارش موجود ترتیب advisory → ردیف سفارش → inventory → رزرو → redemption را رعایت می‌کنند. job فقط try-lock می‌گیرد و skip می‌کند. بازبین تأیید کرد که چرخه‌ای وجود ندارد.
2. **آزادسازی یا شمارش دوباره:** release و redemption release هر دو idempotent‌اند. ردیف سفارش لغو و job را سریال می‌کند.
3. **لغو سفارش پرداخت‌شده یا در حال پرداخت:** اول guard وضعیت بدون اثر جانبی، و قاعده پرداخت در ADR-050.
4. **IDOR:** فیلتر `user_id` و 404.
5. **مصرف اشتباه انقضای lazy:** تصمیم expire/release بعد از lockها گرفته می‌شود.
6. **توقف job:** try-lock، `SKIP LOCKED` و `lock_timeout` موجود.
7. **PII:** فقط id، شماره سفارش و وضعیت.

## Rollback
- `git revert` commit؛ بدون migration. سفارش‌هایی که job لغو کرده سازگار می‌مانند. بعد از revert، سفارش منقضی دوباره `pending_payment` می‌ماند و مانع سفارش جدید نیست (ADR-048). در deploy غلتان job قدیمی lock سفارش نمی‌گیرد؛ مرحله دوم sweep آن حالت را جمع می‌کند. staging روی tmpfs است.

## Tests
- `tests/test_orders_cancel.py`:
  - 200: سفارش `cancelled`/`customer`، رزرو `released`، موجودی آزاد برمی‌گردد، redemption `released`، یک ردیف history (actor = کاربر)، audit `order.status_changed` (با `redemption`) و `reservation.released`. سبد تغییر نمی‌کند. no-store.
  - سفارش بدون کد (redemption `none`).
  - لغو دوم → 200 با همان وضعیت، بدون history یا audit جدید.
  - 401 (حتی با UUID بد)؛ 400 UUID بد؛ 400 query ناشناخته؛ 404 سفارش دیگران و id ناموجود؛ 422 سفارش `confirmed` با رزرو committed (نه 409). شکل خطا و `request_id` روی 404 و 422.
  - وضعیت پرداخت `failed` → لغو می‌شود؛ `pending` → 409 (طبق تصمیم کاربر).
  - lazy: رزرو گذشته از `expires_at` و job اجرانشده → `expired` با actor system. رزرو `expired` بدون لغو سفارش → `expired`.
  - lazy بعد از اینکه اصلاح ادمین بخشی از خطوط را آزاد کرده → شمارنده‌ها درست می‌مانند.
  - بعد از لغو: `POST /orders` جدید موفق است و آخرین استفاده کد سقف‌دار دوباره قابل استفاده است.
  - همزمانی: لغو ∥ لغو (یک history)، لغو ∥ sweep، لغو ∥ اصلاح موجودی ادمین، لغو ∥ سفارش کاربر دیگر روی همان variant؛ بدون deadlock و با invariant `reserved_quantity`.
- `tests/test_reservation_jobs.py`:
  - رزرو منقضی سفارش → `cancelled`/`expired`، redemption آزاد، history با actor NULL، audit با actor None، `cancelled` شمرده می‌شود.
  - advisory سفارش گرفته‌شده → skip. ردیف سفارش قفل‌شده → skip و دور بعد بسته می‌شود.
  - مرحله دوم: سفارش pending با رزرو `expired` → لغو.
  - رزرو بدون سفارش مثل قبل. تست‌های موجود «row held» بازبینی می‌شوند که هنوز همان چیزی را تست کنند که ادعا دارند.
- `tests/test_orders_e2e.py`: سبد مهمان → OTP → ادغام → validate → order → replay → cancel → موجودی و کد برمی‌گردند.
- بقیه فهرست اولیه ORD-06 (idempotency، PRICE_CHANGED، INSUFFICIENT_STOCK، SD rule) در `test_orders_create.py` پوشش داده شده است (۱۸ تست).

## Acceptance Criteria
- [ ] ایجاد تکراری → یک سفارش (موجود)؛ SD rule (موجود + e2e).
- [ ] لغو مشتری فقط در `pending_payment` (و قاعده پرداخت ADR-050)؛ رزرو و redemption در یک تراکنش آزاد می‌شوند؛ idempotent؛ سفارش دیگران → 404.
- [ ] انقضای رزرو (job یا lazy) سفارش را با `expired` لغو می‌کند، redemption را آزاد می‌کند و audit با actor system دارد.
- [ ] ترتیب lock ADR-048 در لغو و job؛ تست‌های همزمانی بالا سبزند.
- [ ] pytest، ruff، format و mypy سبزند.

## Log
- 2026-10-18: plan (جلسه `/phase`، batch ۱؛ چون رزرو را آزاد می‌کند تنها اجرا می‌شود و طبق AUTOPILOT برای تأیید کاربر متوقف می‌شود؛ بازبین opus).
- 2026-10-18: بازبینی plan (opus): APPROVE WITH CHANGES، بدون چرخه deadlock و بدون نیاز به schema. ۱۰ یافته اعمال شد: guard وضعیت قبل از هر اثر جانبی (422 نه 409)؛ تصمیم expire/release بعد از lockها؛ قاعده لغو در وضعیت پرداخت pending/failed (سؤال از کاربر)؛ سفارش pending بدون رزرو active (مرحله دوم sweep و invariant)؛ مسیرهای lazy و اصلاح PLAN.md؛ `FOR UPDATE` کامل؛ بررسی مالکیت قبل از advisory؛ نتیجه redemption در audit؛ تست‌های اضافه؛ rollback در deploy غلتان. منتظر تأیید کاربر.
