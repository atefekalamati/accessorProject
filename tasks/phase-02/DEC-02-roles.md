# DEC-02 — Role set and extra roles (D2)

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 0.5h (estimate) · **Deadline:** — · **Dependencies:** —

## Objective
مجموعه نهایی نقش‌ها.

## PRD reference
«هویت و دسترسی»، «قیمت و مالیات»، «موجودی و رزرو»، «صفحه اصلی»، «دسته‌بندی محصولات»

## Acceptance Criteria
- [x] نقش‌ها: `customer`، `support`، `content_manager`، `admin`، `super_admin`. `finance_manager` و `warehouse_manager` به نسخه بعد موکول شدند.
- [x] ADR-004 ثبت شد و PRD (بخش‌های مرجع) به‌روز شد.
- [x] AUTH-02، AUTH-06، AUTH-11، PRC-05 و ADM-07 مسدود نیستند.

## Implementation Notes
seed فعلی `warehouse_manager` دارد و `super_admin` ندارد؛ اصلاح در AUTH-02.

## Validation
—

## Log
- 2026-09-29: تصمیم کاربر → ADR-004.
