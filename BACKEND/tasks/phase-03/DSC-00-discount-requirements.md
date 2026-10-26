# DSC-00 — Rewrite discount requirements

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** — · **Level:** HIGH

## Objective
بازنویسی بخش قالبی PRD با الزامات دقیق، علامت ✓ و ثبت در جدول PRD changes.

## PRD reference
«کد تخفیف» ✓ و «تخفیف‌ها» ✓؛ «معماری سیستم»، «قیمت و مالیات» ✓، «موجودی و رزرو» ✓. تصمیم‌ها: D31، D33، D34 (ADR-039).

## Acceptance Criteria
- [x] بخش‌ها بازنویسی و ✓ شدند؛ CRUDهای قالبی حذف شدند.
- [x] ردیف جدول PRD changes و تصمیم‌ها در DECISIONS.md.
- [x] تأیید کاربر (2026-10-12، با ۸ تغییر).

## Log
- 2026-10-12: پیش‌نویس مشترک پنج task فاز ۳ (بدون ویرایش PRD)؛ چهار سؤال (D30–D33) و سه افزوده کاربر (D34)؛ خلاصه ≤۸۰ خط فرستاده شد؛ کاربر با ۸ تغییر تأیید کرد (شکست پرداخت رزرو و redemption را نگه می‌دارد، لغو سفارش در انقضا، rate limit کد، قفل DiscountCode، کسر جزئی سبد، Idempotency-Key، مبنای ارسال رایگان و fingerprint، پاک‌شدن cookie). همه ویرایش‌های PRD در یک commit. COMPLETE.
