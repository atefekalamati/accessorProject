# CNT-06 — Contact form / tickets

**Status:** COMPLETE · **Priority:** LOW · **Estimate:** 4h (estimate) · **Deadline:** — · **Dependencies:** CNT-00 · **Level:** MEDIUM

## Objective
`POST /contact` برای مهمان و کاربر با rate limit، و پیگیری پیام‌ها در پنل مدیریت.

## PRD reference
«تماس با ما» ✓؛ ADR-016، ADR-053.

## Acceptance Criteria
- [x] جدول `contact_messages` با migration جدید؛ موبایل E.164 و `user_id` برای کاربر واردشده.
- [x] ۵ پیام در ساعت برای هر IP و ۳ پیام در ساعت برای هر موبایل (قابل تنظیم) → 429 `RATE_LIMITED` با `Retry-After`؛ سقف زیر درخواست همزمان دقیق است.
- [x] `POST /contact` → 201 بدون داده پیام؛ فیلدهای سیستمی کلاینت نادیده گرفته می‌شوند.
- [x] مجوز جدید `contact_messages:manage` (support، admin، super_admin)؛ content_manager → 403.
- [x] انتقال `new → in_progress → closed`؛ انتقال نامعتبر → 422.
- [x] تغییر وضعیت در AuditLog بدون متن پیام؛ log بدون PII.

## Implementation Notes
`app/modules/content/`. سقف‌ها با advisory lock روی کلیدهای IP و موبایل دقیق می‌مانند. پشت proxy به OPS-04 نیاز دارد.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-11-11: فرم تماس: POST /contact برای مهمان و کاربر (201 بدون داده)، سقف دقیق ۵/ساعت IP و ۳/ساعت موبایل با advisory lock و Retry-After، صف ادمین با مجوز جدید contact_messages:manage (support، admin، super_admin)، انتقال new→in_progress→closed، audit بدون متن پیام؛ migration 0030؛ ADR-056. COMPLETE.
