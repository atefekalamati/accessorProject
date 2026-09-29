# FND-02 — Request-id, JSON logging, unified error handlers

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** FND-01

## Objective
هر درخواست یک `request_id` دارد، logها به‌صورت JSON ساختاریافته‌اند و همه خطاها شکل ثابت دارند.

## PRD reference
«معماری سیستم»، «پایش و رخدادها» (قالبی)

## Acceptance Criteria
- [x] هدر `X-Request-ID` (UUID معتبر) منتقل می‌شود و در غیر این صورت ساخته می‌شود. در پاسخ هم برگردانده می‌شود.
- [x] شکل خطا: `{"error":{"code","message","details"},"request_id"}` برای `AppError`، خطای HTTP، validation (امروز 422؛ طبق ADR-011 در INF-01 به 400 تغییر می‌کند) و خطای پیش‌بینی‌نشده (500).
- [x] log JSON شامل method، path، status و duration.

## Implementation Notes
`app/core/middleware.py`، `app/core/logging.py`، `app/core/errors.py`. کاتالوگ کد خطا در INF-01 و redaction در INF-06 انجام می‌شود.

## Validation
```powershell
python -m pytest tests/test_health.py
```

## Log
- 2026-09-13: پیاده‌سازی شد (commit `48f1542`).
- 2026-09-29: تأیید شد (`test_http_errors_have_stable_contract`، `test_valid_request_id_is_propagated`).
