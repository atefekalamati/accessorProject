# AUTH-11 — Admin user endpoints (list, status, role) + AuditLog

**Status:** COMPLETE · **Priority:** MEDIUM · **Estimate:** 5h (estimate) · **Deadline:** — · **Dependencies:** AUTH-10, INF-03, INF-05, ADR-004 · **Level:** HIGH

## Objective
مدیریت کاربران توسط مدیران مجاز.

## PRD reference
«هویت و دسترسی» ✓

## Acceptance Criteria
- [x] `GET /admin/users` صفحه‌بندی دارد و با شماره، وضعیت و نقش جست‌وجو می‌شود.
- [x] `PATCH /admin/users/{id}/status` کاربر را فعال، غیرفعال یا مسدود می‌کند. غیرفعال‌کردن همه sessionهای کاربر را باطل می‌کند.
- [x] `PATCH /admin/users/{id}/role` **فقط توسط Super Admin** انجام می‌شود. Admin نمی‌تواند خودش یا دیگران را به Super Admin ارتقا دهد (403).
- [x] غیرفعال‌کردن مدیران فقط توسط Super Admin انجام می‌شود.
- [x] هر تغییر نقش و وضعیت در `audit_logs` با before/after ثبت می‌شود.
- [x] تخصیص نقش فقط نقش‌های موجود در `DEFAULT_ROLES` (`app/db/seed.py`) را می‌پذیرد. نقش دیگر، حتی اگر ردیفش در دیتابیس باشد (مثل `warehouse_manager` یا `legacy_role`)، رد می‌شود.
- [x] یک data migration جدید `warehouse_manager` را حذف می‌کند، **فقط اگر** هیچ ردیفی در `user_roles` به آن ارجاع نداشته باشد. downgrade آن ردیف را با همان id و مقادیر migration `20260913_0001` دوباره insert می‌کند. تست‌های این migration هم به‌روزرسانی `HEAD_REVISION` و هم هر دو حالت (با ارجاع و بدون ارجاع) را پوشش می‌دهند.

## Implementation Notes
`app/modules/admin/` (تصمیم plan). جزئیات قواعد در ADR-019.

## Validation
```powershell
python -m pytest   # با TEST_DATABASE_URL
python -m mypy app tests
```

## Log
### 2026-10-06 — scope اضافه شد (تصمیم کاربر)
- data migration برای حذف `warehouse_manager` و محدودکردن تخصیص نقش به `DEFAULT_ROLES`. برآورد 4h → 5h.
### 2026-10-09 — COMPLETE (batch AUTH-11/12)
- ماژول `app/modules/admin/` (router، service، repository، schemas، dependencies) با سه endpoint زیر `/api/v1/admin/users`.
- list: مجوز `users:read` که قبل از allowlist query چک می‌شود. `page`/`limit` (حداکثر 100)، فیلترهای `mobile` (جست‌وجوی جزئی رقمی؛ صفر ابتدای شماره محلی حذف می‌شود)، `status`، `role` (فقط `DEFAULT_ROLES`) و `sort` (`newest`/`oldest`). پارامتر ناشناخته → 400. رکورد soft-deleted نمی‌آید.
- status: مجوز `users:manage`، که حالا admin هم دارد (seed؛ ADR-004 به‌روز شد). admin فقط هدفی را تغییر می‌دهد که نقش‌هایش زیرمجموعه `{customer}` است. هر نقش staff فقط با super_admin، وگرنه 403. تغییر وضعیت خود → 422. `inactive` و `blocked` همه sessionها را revoke می‌کنند.
- role: مجوز `users:manage_roles` به‌علاوه چک صریح نقش `super_admin`. body `{"roles": [...]}` کل مجموعه را جایگزین می‌کند. فقط `DEFAULT_ROLES`، یکتا، ۱ تا ۵ نقش؛ در غیر این صورت 400. تغییر نقش خود → 422.
- آخرین super_admin فعال حذف یا غیرفعال نمی‌شود (409 `CONFLICT`، advisory lock `rbac:super_admin`). با درخواست‌های همزمان در سطح service تست شد.
- audit: `user.status_changed` (status و `revoked_sessions`) و `user.roles_changed` (roles). تغییرِ بی‌اثر audit ندارد.
- migration `20261009_0005` (فقط data): `warehouse_manager` را فقط بدون ارجاع حذف می‌کند. downgrade آن را با id و مقادیر 0001 برمی‌گرداند. `HEAD_REVISION` به‌روز شد.
- تست‌ها: `tests/test_admin_users.py` (۶۱ مورد، شامل هر چهار نقش staff) و ۲ تست migration در `tests/test_database.py` (با ارجاع و بدون ارجاع).
- Validation: pytest 616 passed (با دیتابیس تست)، ruff، format و mypy سبز.
- برای دیتابیس توسعه لازم است: `alembic upgrade head` و `python -m app.db.seed` (grant جدید `users:manage` برای admin).
