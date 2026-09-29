# DEC-12 — Unified error format, 400 vs 422 (D12)

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 0.5h (estimate) · **Deadline:** — · **Dependencies:** —

## Objective
تأیید فرمت خطا و مرز 400 و 422.

## PRD reference
«معماری سیستم» (خطاهای کلیدی)

## Acceptance Criteria
- [x] فرمت `{"error":{"code","message","details"},"request_id"}` تأیید شد.
- [x] قاعده: validation → **400** (`VALIDATION_ERROR`)؛ نقض قانون کسب‌وکار → **422**.
- [x] ADR-011 ثبت شد؛ تغییر رفتار فعلی (validation امروز 422 است) در INF-01 انجام می‌شود.

## Implementation Notes
فقط فایل‌های برنامه‌ریزی.

## Validation
—

## Log
- 2026-09-29: تصمیم کاربر → ADR-011 (برخلاف پیشنهاد اولیه Claude که validation را 422 می‌دانست).
