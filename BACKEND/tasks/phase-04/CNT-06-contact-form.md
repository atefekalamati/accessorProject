# CNT-06 — Contact form / tickets

**Status:** NOT_STARTED · **Priority:** LOW · **Estimate:** 4h (estimate) · **Deadline:** — · **Dependencies:** CNT-00 · **Level:** MEDIUM

## Objective
`POST /contact` برای مهمان و کاربر با rate limit، و پیگیری پیام‌ها در پنل مدیریت.

## PRD reference
«تماس با ما» ✓؛ ADR-016، ADR-053.

## Acceptance Criteria
- [ ] جدول `contact_messages` با migration جدید؛ موبایل E.164 و `user_id` برای کاربر واردشده.
- [ ] ۵ پیام در ساعت برای هر IP و ۳ پیام در ساعت برای هر موبایل (قابل تنظیم) → 429 `RATE_LIMITED` با `Retry-After`؛ سقف زیر درخواست همزمان دقیق است.
- [ ] `POST /contact` → 201 بدون داده پیام؛ فیلدهای سیستمی کلاینت نادیده گرفته می‌شوند.
- [ ] مجوز جدید `contact_messages:manage` (support، admin، super_admin)؛ content_manager → 403.
- [ ] انتقال `new → in_progress → closed`؛ انتقال نامعتبر → 422.
- [ ] تغییر وضعیت در AuditLog بدون متن پیام؛ log بدون PII.

## Implementation Notes
`app/modules/content/`. سقف‌ها با advisory lock روی کلیدهای IP و موبایل دقیق می‌مانند. پشت proxy به OPS-04 نیاز دارد.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
