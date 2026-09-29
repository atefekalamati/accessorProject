# DEC-07 — HTTP 410 for expired reservation (D7)

**Status:** COMPLETE · **Priority:** MEDIUM · **Estimate:** 0.5h (estimate) · **Deadline:** — · **Dependencies:** —

## Objective
تعیین پاسخ API برای رزرو منقضی‌شده.

## PRD reference
«موجودی و رزرو»

## Acceptance Criteria
- [x] انتخاب شد: `409` با `code: RESERVATION_EXPIRED`؛ کد 410 استفاده نمی‌شود.
- [x] ADR-008 ثبت شد؛ PRD «موجودی و رزرو» به‌روز شد؛ INF-01 و INV-05 مسدود نیستند.

## Implementation Notes
فقط فایل‌های برنامه‌ریزی و PRD.

## Validation
—

## Log
- 2026-09-29: تصمیم کاربر → ADR-008.
