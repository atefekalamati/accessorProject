# PAY-03 — Callback: verify, amount == grandTotal, idempotent, commit reservation

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 5h (estimate) · **Deadline:** — · **Dependencies:** PAY-02, INV-05 · **Level:** HIGH

## Objective
callback نامطمئن → verify سمت سرور → اعمال نتیجه در یک تراکنش با ترتیب lock ADR-048؛ D32 و تصمیم‌های ADR-051.

## PRD reference
«پرداخت» ✓؛ ADR-048، ADR-049، ADR-050، ADR-051؛ D31، D32، D34؛ [M3.5-PLAN.md](../../docs/project/M3.5-PLAN.md).

## Acceptance Criteria
- [x] duplicate callback changes nothing (تکراری و ×۳ همزمان → یک اعمال).
- [x] success removes only ordered quantities from the cart (D34)؛ کد سفارش از سبد برداشته می‌شود.
- [x] late success → refund_required + audit + WARNING log (D32)؛ با و بدون sweep.
- [x] branch on `CommitOutcome` (EXPIRED never marks paid, tested).
- [x] mismatch → refund_required (`amount_mismatch`)، ERROR log، audit؛ رزرو مصرف نمی‌شود؛ سفارش قابل پرداخت می‌ماند (ADR-051).
- [x] پاسخ 200 با outcome برای هر callback پردازش‌شده؛ ref ناشناخته 404؛ بدنه نامعتبر یا بزرگ 400؛ rate limit 429؛ event redact‌شده (بدون کارت).
- [x] پرداخت دوم روی سفارش paid → `duplicate_payment`؛ FAILED دیرهنگام فقط ردیف payment را تغییر می‌دهد.
- [x] callback جعلی: فقط verify تصمیم می‌گیرد.
- [x] supersede در init با verify PAID اکنون نتیجه را اعمال می‌کند (جایگزین 409 موقت PAY-02).

## Log
- 2026-10-25: پیاده‌سازی (plan مشترک M3.5). `PaymentProcessor.apply` بین callback، supersede و reconciliation مشترک است.
  - بازبینی diff (opus): PASS WITH CHANGES، بدون deadlock و بدون مصرف دوباره.
  - اعمال شد:
    - mismatch فقط order payment تلاش زنده را `failed` می‌کند؛ سفارش لغوشده → `refund_required`.
    - سقف بدنه قبل از خواندن (Content-Length و stream).
    - خطای بلند وقتی paid نمی‌شود.
    - `cart.updated_at` به‌روز می‌شود.
    - FAILED بعد از paid log می‌شود.
    - متن ADR-051 اصلاح شد.
    - IP جدا برای هر callback در تست‌ها (rate limit تست‌ها را به هم وابسته نکند).
    - تست‌های اضافه: paid دیرهنگام روی failed، mismatch روی تلاش قدیمی و روی سفارش لغوشده، حذف خط هم‌اندازه و نگه‌داشتن کد دیگر، 503 verify، ref غیررشته‌ای.
  - pytest (1974)، ruff، format و mypy سبز. COMPLETE.
