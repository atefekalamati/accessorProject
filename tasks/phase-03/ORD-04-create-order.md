# ORD-04 — POST /orders (verified mobile, reserve 15 min, snapshot)

**Status:** IN_PROGRESS (plan منتظر تأیید کاربر) · **Priority:** HIGH · **Estimate:** 5h (estimate) · **Deadline:** — · **Dependencies:** ORD-01, ORD-02, ORD-03, INV-04, DSC-05 · **Level:** HIGH

## Objective
ثبت سفارش از سبد کاربر در یک تراکنش: quote دوباره و مقایسه fingerprint، رزرو ۱۵ دقیقه‌ای، redemption pending کد، snapshot کامل؛ idempotent با `Idempotency-Key`. سبد خالی نمی‌شود.

## PRD reference
«نتیجه سفارش» ✓ (`POST /orders`)؛ «موجودی و رزرو» ✓؛ ADR-007، ADR-031، ADR-036، ADR-039 (D31، D34)، ADR-044، ADR-045، ADR-046، ADR-047.

## Plan
- `POST /api/v1/orders` در `app/modules/orders/{schemas,service,router}.py`:
  - ترتیب dependency: `get_current_user` (401؛ ورود فقط با OTP، پس موبایل تأییدشده؛ کاربر بدون phone → 401 `MOBILE_NOT_VERIFIED` دفاعی) → `idempotency_key` (400) → بدنه `{address_id, shipping_method_id, fingerprint}` (`extra=forbid`، fingerprint ۶۴ hex؛ وگرنه 400). مبلغی از کلاینت پذیرفته نمی‌شود.
  - یک تراکنش، با ترتیب lock سراسری (ADR-044/046/047):
    1. `IdempotencyService.begin(scope="orders.create", hash(body))` → replay (201 قبلی) یا 422 `IDEMPOTENCY_KEY_REUSED`.
    2. سبد کاربر `FOR UPDATE` (`find_user_cart(lock=True)`؛ نبود/خالی → 422 `cart_empty`). دلیل: خواندن سازگار خطوط و `discount_code_id`؛ با مسیرهای نوشتن سبد (سبد → خواندن variant) و ادغام (سبد کاربر → سبد مهمان) چرخه ندارد.
    3. اگر سبد کد دارد: `RedemptionService.lock_code(cart.discount_code_id)` (**قفل کد قبل از درج سفارش**؛ بازبینی plan: FK `orders.discount_code_id` روی ردیف کد `FOR KEY SHARE` می‌گیرد و `FOR UPDATE` بعدی redeem با KEY SHARE تراکنش همزمان deadlock می‌کرد). `now = utc_now()` بعد از lockها (مثل INV-05).
    4. `CheckoutService.build_quote(..., locked_code=..., check_stock=False)`. خطاهای 422/404 آن (سبد، آدرس، روش، خط، کد ردشده → 422 `DISCOUNT_NOT_APPLICABLE`) قبل از مقایسه fingerprint می‌آیند. fingerprint متفاوت → 409 `PRICE_CHANGED` با quote جدید در `details[0].quote` و `Cache-Control: no-store` (هیچ چیزی ذخیره نمی‌شود).
    5. `order_id = uuid4()`، شماره از `order_number_seq`، `created_at = updated_at = now` (CHECK سال). درج `Order` و **flush** قبل از reserve/redeem (FK آن‌ها به orders).
    6. `ReservationService.reserve(order_id, lines, user_id, cart_id, now)` (advisory سفارش → variant → inventory `FOR UPDATE`): ناکافی → 409 `INSUFFICIENT_STOCK` (فقط از reserve)؛ غیرقابل‌فروش → 422.
    7. اگر کد اعمال شده: `RedemptionService.redeem(priced_rules=quote.priced_rules, ...)` روی ردیفی که از قبل قفل شده (قواعد ثابت‌اند)؛ سقف پر → 422.
    8. درج `OrderItem`ها (position = ترتیب id خط، snapshot عنوان، SKU، برچسب گزینه‌ها `key: value / ...` مرتب، اجزای خط طبق ADR-031)، `OrderPriceSnapshot` (policy، fingerprint quote، هزینه و سقف روش)، `OrderAddress` (کپی، `source_address_id`)، `OrderStatusHistory` (سه ردیف ایجاد: old=NULL)، audit `order.created` (بدون PII: شماره سفارش، مبلغ کل، تعداد خطوط).
    9. assert سرآیند = Σ خطوط (subtotal، تخفیف محصول، کد، مالیات) و `grand_total` = pricing؛ ناسازگاری → RuntimeError (500، باگ).
    10. `IdempotencyService.complete(201, body)` و پاسخ 201 با `Cache-Control: no-store`.
  - **ترتیب سراسری جدید lock** (ADR-044/046/047 به‌روز می‌شوند، همراه docstringهای `redemption.py`، `idempotency.py`، `state_service.py`): idempotency → سبد → **کد** → advisory سفارش → ردیف سفارش → inventory → redemption. هیچ مسیری inventory و بعد کد را قفل نمی‌کند (job انقضا، confirm و release فقط ردیف redemption؛ ویرایش ادمین فقط کد).
  - **replay:** همیشه همان 201 اولیه، حتی اگر رزرو منقضی یا سفارش لغو شده باشد (ADR-046)؛ وضعیت فعلی از `GET /orders/{number}` (ORD-06/ACC-01).
  - پاسخ `OrderResponse`: id، `order_number`، سه وضعیت، اجزای مبلغ، currency، خطوط snapshot، آدرس، روش ارسال و مبلغ، کد و مبلغ، `reservation_expires_at`، `created_at`.
  - سبد خالی نمی‌شود (D34-4)؛ دو `POST` با کلیدهای متفاوت روی یک سبد دو سفارش جدا می‌سازند (سریال روی lock سبد؛ موجودی و سقف کد محافظت می‌کنند).
- بدون migration و بدون تغییر schema.

## Risks
1. **سفارش تکراری** (retry شبکه): Idempotency-Key + advisory lock؛ تست replay، بدنه متفاوت 422، و `gather` همان کلید → یک سفارش.
2. **oversell**: reserve با row lock (ADR-036)؛ تست دو کاربر همزمان برای آخرین واحد → یک 201 و یک 409، invariant `reserved_quantity`.
3. **عبور از سقف کد**: redeem زیر قفل ردیف کد (ADR-044)؛ تست همزمانی آخرین استفاده → یک 201 و یک 422.
4. **قیمت متفاوت از quote**: fingerprint quote (ORD-03) + قواعد کد در redeem؛ تست تغییر قیمت/کد/روش بعد از validate → 409 با quote جدید و بدون ردیف.
5. **deadlock**: ترتیب lock ثابت (idempotency → سبد → کد → advisory سفارش → inventory → redemption؛ کد قبل از درج سفارش به‌خاطر KEY SHARE ناشی از FK)؛ تست دو کاربر با یک کد (هر دو 201) و دو سفارش متقاطع چند-variant بدون deadlock.
6. **نوشتن نیمه‌کاره**: یک تراکنش؛ تست شکست بعد از reserve (مثلاً redeem 422) → نه سفارش، نه رزرو، نه redemption، نه ردیف idempotency.
7. **ناسازگاری مبالغ**: assert سرآیند = Σ خطوط + CHECKهای ORD-01.
8. **PII**: log/audit فقط شماره سفارش و مبالغ؛ پاسخ no-store؛ بدنه ذخیره‌شده idempotency با CASCADE کاربر و TTL.
9. **SD rule**: خط حذف‌شده → 422 قبل از هر نوشتن.

## Rollback
- `git revert` commit؛ بدون migration. سفارش‌های ایجادشده در staging (tmpfs) با redeploy پاک می‌شوند؛ رزروها با job انقضا آزاد می‌شوند.

## Extra tests (`tests/test_orders_create.py`)
- 201 کامل: snapshot خطوط و آدرس و روش، position به ترتیب id خط، مبالغ = quote، reservation active با `expires_at = now + 15m`، redemption pending، history سه ردیف، audit؛ سبد بدون تغییر.
- replay با همان کلید (همان بدنه، یک سفارش)؛ بدنه متفاوت 422؛ کلید نبود 400؛ 401؛ آدرس دیگران 404؛ روش غیرفعال 422؛ سبد خالی 422؛ کد ردشده 422؛ fingerprint کهنه 409 با quote؛ موجودی 409؛ خط حذف‌شده 422.
- همزمانی: آخرین واحد (دو کاربر)، آخرین استفاده کد، همان کلید ×۳، سفارش‌های متقاطع.
- rollback کامل در شکست redeem بعد از reserve.
- دو کاربر با یک کد و ظرفیت کافی همزمان → هر دو 201 (بدون deadlock).
- کد بعد از validate منقضی/غیرفعال → 422؛ مقدار کد عوض شود ولی اعمال شود → 409 با quote؛ 409 با no-store.
- retry همان کلید بعد از 409/422 → اجرای تازه (چیزی ذخیره نشده).
- کاربر بدون phone معتبر → 401؛ `now` تزریقی در مرز سال (سال شماره = سال `created_at`).
- replay بعد از لغو سفارش همان 201 قدیمی را برمی‌گرداند.
- ADR-031: ترتیب ورودی خطوط به‌هم‌ریخته → خروجی یکسان (ترتیب درج آیتم‌های سبد متفاوت، position و مبالغ یکسان).

## Acceptance Criteria
- [ ] idempotent؛ transactional؛ DiscountCode FOR UPDATE + pending redemption (D31)؛ cart not cleared (D34).
- [ ] SD rule (test)؛ pricing lines in stable order (by line id) + shuffled input → identical output (ADR-031).
- [ ] تست‌های همزمانی و rollback بالا.
- [ ] pytest، ruff، format و mypy سبز.

## Log
- 2026-10-18: plan (batch ۴ جلسه phase؛ تنها، به دستور کاربر برای تأیید متوقف می‌شود؛ بازبین opus).
- 2026-10-18: بازبینی plan (opus): APPROVE WITH CHANGES؛ اعمال شد: قفل کد قبل از درج سفارش (deadlock KEY SHARE/FOR UPDATE) و ترتیب سراسری جدید lock، no-store روی 409، `now` بعد از lockها، flush سفارش قبل از reserve، معنای replay، تست‌های اضافه. منتظر تأیید کاربر.
