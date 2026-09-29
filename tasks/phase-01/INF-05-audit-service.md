# INF-05 — AuditLog writer service

**Status:** NOT_STARTED · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** FND-04

## Objective
یک تابع واحد برای ثبت رخداد حساس در **همان تراکنش** عملیات.

## PRD reference
«هویت و دسترسی» ✓، «قیمت و مالیات» ✓، «موجودی و رزرو» ✓

## Acceptance Criteria
- [ ] `record_audit(session, *, actor_id, action, entity_type, entity_id, before, after, request)` پیاده‌سازی شده است.
- [ ] `request_id`، IP و diff در `metadata` (JSONB) ذخیره می‌شوند. **پیشنهاد:** بدون migration، چون جدول ستون `request_id` ندارد.
- [ ] فیلدهای حساس (token، hash، کد OTP) قبل از ذخیره حذف می‌شوند.
- [ ] نام action از قرارداد `<entity>.<verb>` پیروی می‌کند (مثلاً `product.price_changed`).
- [ ] rollback عملیات، رکورد audit را هم rollback می‌کند (تست integration).

## Implementation Notes
`app/shared/audit.py` و `tests/test_audit.py` (هر دو فایل جدید و برنامه‌ریزی‌شده). مدل `app/db/models/audit.py` از قبل موجود است.

## Validation
```powershell
python -m pytest   # با TEST_DATABASE_URL
python -m ruff check .
python -m ruff format --check .
python -m mypy app tests
```

## Log
- 2026-09-29: از `tasks/M1-05-audit-service.md` منتقل شد.
