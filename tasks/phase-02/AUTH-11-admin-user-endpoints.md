# AUTH-11 — Admin user endpoints (list, status, role) + AuditLog

**Status:** NOT_STARTED · **Priority:** MEDIUM · **Estimate:** 5h (estimate) · **Deadline:** — · **Dependencies:** AUTH-10, INF-03, INF-05, ADR-004 · **Level:** HIGH

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
- [ ] تخصیص نقش فقط نقش‌های موجود در `DEFAULT_ROLES` (`app/db/seed.py`) را می‌پذیرد. نقش دیگر، حتی اگر ردیفش در دیتابیس باشد (مثل `warehouse_manager` یا `legacy_role`)، رد می‌شود.
- [ ] یک data migration جدید `warehouse_manager` را حذف می‌کند، **فقط اگر** هیچ ردیفی در `user_roles` به آن ارجاع نداشته باشد. downgrade آن ردیف را با همان id و مقادیر migration `20260913_0001` دوباره insert می‌کند. تست‌های این migration هم به‌روزرسانی `HEAD_REVISION` و هم هر دو حالت (با ارجاع و بدون ارجاع) را پوشش می‌دهند.

## Implementation Notes
`app/modules/admin/` یا `app/modules/auth/` (تصمیم در گام plan).

## Validation
```powershell
python -m pytest   # با TEST_DATABASE_URL
python -m mypy app tests
```

## Log
### 2026-10-06 — scope اضافه شد (تصمیم کاربر)
- data migration برای حذف `warehouse_manager` و محدودکردن تخصیص نقش به `DEFAULT_ROLES`. برآورد 4h → 5h.
