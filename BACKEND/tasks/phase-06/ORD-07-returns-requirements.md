# ORD-07 — Rewrite «مرجوعی» requirements

**Status:** IN_PROGRESS · **Priority:** LOW · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** — · **Level:** HIGH

## Objective
بازنویسی بخش قالبی «مرجوعی» با الزامات دقیق؛ تعیین مبلغ بازپرداخت، بازگشت موجودی و شکستن ORD-08.

## PRD reference
«مرجوعی» (قالبی)؛ «موجودی و رزرو» ✓ («مرجوعی فقط پس از تأیید سلامت کالا موجودی را افزایش می‌دهد»)؛ «مدیریت سفارش» ✓؛ D35، ADR-053، ADR-054، ADR-062.

## Acceptance Criteria
- [ ] پیش‌نویس زیر را کاربر تأیید کرد (R1، R2).
- [ ] بخش «مرجوعی» بازنویسی و ✓ شد؛ CRUD قالبی حذف شد.
- [ ] ADR و ردیف PRD changes در DECISIONS.md؛ PLAN با taskهای شکسته‌شده ORD-08.

## Implementation Notes — پیش‌نویس (تأییدنشده)
- درخواست فقط برای سفارش خود کاربر با shipment `delivered`، حداکثر `RETURN_WINDOW_DAYS` (پیش‌فرض ۷، `Settings`) روز بعد از `delivered_at`. سفارش دیگران یا ناموجود → 404.
- درخواست به‌ازای هر قلم: تعداد ≤ خریده‌شده منهای درخواست‌های باز یا پذیرفته‌شده قبلی (→ 422). دلیل از allowlist، توضیح اختیاری (≤۱۰۰۰). Idempotency-Key مثل `POST /orders`.
- وضعیت‌ها: `requested → approved | rejected`، `approved → received → inspected`، سپس `refund_required → refunded`. لغو توسط مشتری فقط در `requested`. هر انتقال: history و audit.
- بازرسی برای هر قلم `sellable` یا `damaged`. فقط `sellable` موجودی را زیاد می‌کند: movement `return` روی انبار پیش‌فرض با row lock، در همان تراکنش. `damaged` موجودی را تغییر نمی‌دهد.
- R1 (پیشنهاد): مبلغ بازپرداخت = `final_line_total × تعداد پذیرفته ÷ تعداد خرید`، گردکردن به پایین. اگر کل قلم برگردد، خود `final_line_total`. هزینه ارسال برگردانده نمی‌شود. ثبت بازپرداخت دستی با `refund_reference` unique، مثل ADM-08.
- R2 (پیشنهاد): لغو سفارش پرداخت‌شده و ارسال‌نشده توسط ادمین (D35) به‌عنوان task جدید ORD-11 (2h، HIGH): payment به `refund_required` می‌رود و موجودی commitشده با movement `return` برمی‌گردد. یا POST_LAUNCH بماند.
- مجوزها: `returns:manage` (support، admin، super_admin)؛ ثبت بازپرداخت با `payments:refund`.
- API: `POST /orders/{order_number}/returns`، `GET /returns`، `GET /returns/{id}`، `POST /returns/{id}/cancel`؛ پنل: `GET /admin/returns`، `GET /admin/returns/{id}`، `POST /admin/returns/{id}/{approve|reject|receive|inspect|refund}`.
- شکستن ORD-08 (6h): ORD-08 مدل، migration و API مشتری (2.5h، HIGH)؛ ORD-09 بررسی، دریافت، بازرسی و افزایش موجودی (2.5h، HIGH، opus)؛ ORD-10 بازپرداخت (1.5h، HIGH، opus).

## Validation
فقط PRD و DECISIONS؛ suite بدون تغییر.

## Log
- 2026-11-13: پیش‌نویس در گفت‌وگو فرستاده شد. کاربر scope فاز ۶ را تأیید کرد (ADR-062). R1 و R2 منتظر تأیید هستند.
