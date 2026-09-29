# AUTH-11 — Admin user endpoints (list, status, role) + AuditLog

**Status:** NOT_STARTED · **Priority:** MEDIUM · **Estimate:** 4h (estimate) · **Deadline:** — · **Dependencies:** AUTH-10, INF-03, INF-05, ADR-004

## Objective
مدیریت کاربران توسط مدیران مجاز.

## PRD reference
«هویت و دسترسی» ✓

## Acceptance Criteria
- [ ] `GET /admin/users` صفحه‌بندی دارد و با شماره، وضعیت و نقش جست‌وجو می‌شود.
- [ ] `PATCH /admin/users/{id}/status` کاربر را فعال، غیرفعال یا مسدود می‌کند. غیرفعال‌کردن همه sessionهای کاربر را باطل می‌کند.
- [ ] `PATCH /admin/users/{id}/role` **فقط توسط Super Admin** انجام می‌شود. Admin نمی‌تواند خودش یا دیگران را به Super Admin ارتقا دهد (403).
- [ ] غیرفعال‌کردن مدیران فقط توسط Super Admin انجام می‌شود.
- [ ] هر تغییر نقش و وضعیت در `audit_logs` با before/after ثبت می‌شود.

## Implementation Notes
`app/modules/admin/` یا `app/modules/auth/` (تصمیم در گام plan).

## Validation
```powershell
python -m pytest   # با TEST_DATABASE_URL
python -m mypy app tests
```

## Log
