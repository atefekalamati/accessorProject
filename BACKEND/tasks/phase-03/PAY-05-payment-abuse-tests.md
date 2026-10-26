# PAY-05 — Callback tests (duplicate, amount mismatch, expired)

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** PAY-03, PAY-04 · **Level:** HIGH

## Objective
پوشش مسیرهای سوءاستفاده و رقابت پرداخت (فهرست الزامی کاربر در ADR-049).

## PRD reference
«پرداخت» ✓؛ ADR-049، ADR-051، D32؛ [M3.5-PLAN.md](../../docs/project/M3.5-PLAN.md).

## Acceptance Criteria (abuse paths covered)
- [x] callback دوباره و همزمان (`test_payments_callback.py`)؛ تکرار بعد از refund → `already_processed` و یک audit.
- [x] callback بعد از لغو مشتری (هر دو ترتیب، اجباری با صف lock) و بعد از انقضا (sweep یا lazy).
- [x] مبلغ ناهمخوان (`test_payments_callback.py`).
- [x] callback جعلی و ref ناشناخته (`test_payments_callback.py`).
- [x] همزمانی پرداخت موفق با sweep انقضا: رقابت آزاد (بدون deadlock، هرگز فروش رزرو منقضی)، callback اول (اجباری)، و sweep روی رزرو زنده (فروخته).
- [x] موفق ∥ سفارش جدید همان مشتری؛ init ∥ callback؛ لغو در حین پرداخت (409/422)؛ محصول حذف‌شده بعد از سفارش هنوز فروخته می‌شود.
- [x] tx2 ∥ `request_lost` در هر دو جهت؛ همان کلید بعد از 409 از نو شروع می‌شود؛ no-store.

## Log
- 2026-10-25: تست‌ها (plan مشترک M3.5).
  - بازبینی (opus): PASS WITH CHANGES.
  - **باگ واقعی (D32):** `_paid` مقدار `now` را قبل از lockهای `commit()` می‌گرفت و به آن پاس می‌داد. اگر commit پشت lock کالا منتظر می‌ماند، رزروی که در این فاصله منقضی شده بود مصرف می‌شد. رفع: commit زمانش را خودش بعد از lockها می‌گیرد.
  - اعمال شد:
    - ترتیب‌های اجباری با صف advisory lock.
    - assertion دقیق وضعیت رزرو.
    - کد خطای دقیق در رقابت سفارش جدید.
    - کلید صریح idempotency.
    - تست‌های اضافه: تکرار بعد از refund، محصول حذف‌شده، init ∥ callback، reconciliation بعد از tx2.
  - ۵ اجرای پشت هم با xdist سبز؛ pytest (2002)، ruff، format و mypy سبز. COMPLETE.
