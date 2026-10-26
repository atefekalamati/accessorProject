# PAY-02 — POST /payments/init

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** PAY-01, ORD-04 · **Level:** HIGH

## Objective
شروع یا ادامه پرداخت سفارش؛ مبلغ فقط `grand_total` از DB؛ بدون نگه‌داشتن lock در طول فراخوانی درگاه.

## PRD reference
«پرداخت» ✓؛ ADR-049، ADR-050، ADR-051؛ [M3.5-PLAN.md](../../docs/project/M3.5-PLAN.md).

## Acceptance Criteria
- [x] amount = grandTotal from DB؛ مبلغ کلاینت → 400.
- [x] Idempotency-Key (replay، بدنه متفاوت 422). duplicate با همان کلید در حین فراخوانی درگاه → 409.
- [x] 401 قبل از 400 (query و header)؛ 404 سفارش دیگران؛ 422 سفارش غیرقابل‌پرداخت؛ 409 `RESERVATION_EXPIRED` (lazy cancel، یا too_late).
- [x] ادامه session معتبر (همان redirect، پاسخ زیر کلید جدید هم ذخیره می‌شود).
- [x] session منقضی → verify؛ فقط FAILED قطعی بسته می‌شود؛ PAID/PENDING → 409.
- [x] درخواست در جریان → 409؛ بعد از stale → `request_lost` و payment جدید.
- [x] درگاه بی‌پاسخ/کند/خطای adapter → payment `failed` (`gateway_error`) و 503 یا 500؛ سفارش قابل پرداخت می‌ماند.
- [x] رزرو تمام‌شده در حین فراخوانی → payment بسته و 409.
- [x] production → 503؛ router فقط-dev درگاه fake (صفحه و complete).
- [x] همزمانی: init ∥ init، همان کلید ×۳، init ∥ لغو، init ∥ sweep.

## Log
- 2026-10-19: پیاده‌سازی (plan مشترک M3.5).
  - بازبینی diff (opus): PASS WITH CHANGES، بدون deadlock یا باگ پول.
  - اعمال شد:
    - session منقضی با verify PENDING بسته نمی‌شود و 409 `session_open` می‌گیرد. تفسیر محافظه‌کارانه تصمیم ۳ کاربر، تا شارژ دوباره ممکن نباشد؛ در ADR-051.
    - خطای غیرشبکه‌ای adapter هم payment را می‌بندد.
    - tx2 بعد از لغو یا انقضا payment را می‌بندد.
    - سفارش لغوشده به دلیل انقضا → 409 (نه 422).
    - log در 503 supersede؛ docstringها؛ تست‌های اضافه.
  - flaky واقعی در suite موازی:
    - `test_cancelled_sweep_does_not_keep_the_job_lock`. توضیح اول (advisory مانده از sweep لغوشده) اشتباه بود و با instrumentation رد شد.
    - علت واقعی: helper `_wait_for_lock_waiter` همه pollها را در یک تراکنش اجرا می‌کرد. `pg_stat_activity` برای کل تراکنش cache می‌شود، پس backendی که بعد از poll اول وصل شده بود هرگز دیده نمی‌شد. وقتی sweep اتصال تازه‌ای از pool می‌گرفت، تست fail می‌شد.
    - اصلاح: یک تراکنش جدید برای هر poll (commit `fix(tests)` بعدی). ۲۰ اجرای پشت هم با xdist سبز شد.
    - assertion جدید همزمانی متن JSON را مقایسه می‌کرد (JSONB ترتیب کلید را عوض می‌کند)؛ به مقایسه json اصلاح شد.
  - pytest (1956)، ruff، format و mypy سبز. COMPLETE.
