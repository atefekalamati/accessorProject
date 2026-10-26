# AUTH-02 — Base roles & permissions seed

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** FND-05, ADR-004 · **Level:** HIGH

## Objective
جدول‌های `roles`، `permissions`، `user_roles` و `role_permissions` از قبل موجودند. این task مجموعه نهایی نقش‌ها و کلیدهای permission را seed می‌کند.

## PRD reference
«هویت و دسترسی» ✓. نقش‌های اضافه در «قیمت و مالیات» ✓، «موجودی و رزرو» ✓، «صفحه اصلی» ✓ و «دسته‌بندی محصولات» ✓ آمده‌اند.

## Acceptance Criteria
- [x] نقش‌ها دقیقاً طبق ADR-004: `customer`، `support`، `content_manager`، `admin`، `super_admin`. Guest نقش دیتابیسی نیست.
- [x] `warehouse_manager` از `DEFAULT_ROLES` حذف شد. اگر ردیف آن در دیتابیس توسعه مانده، حذف آن فقط با تأیید کاربر است.
- [x] کلیدهای permission به شکل `<module>:<action>` هستند (مثلاً `pricing:update`، `inventory:update`، `users:manage_roles`) و در یک ثابت کد تعریف شده‌اند.
- [x] `role_permissions` برای هر نقش seed شده و `super_admin` همه permissionها را دارد.
- [x] seed idempotent است و نقش‌ها و permissionهای حذف‌شده از فهرست را پاک نمی‌کند، فقط upsert می‌کند.
- [x] تست seed به‌روز شده است.

## Implementation Notes
`app/db/seed.py`، `tests/test_database.py`.

## Validation
```powershell
python -m app.db.seed
python -m pytest   # با TEST_DATABASE_URL
python -m mypy app tests
```

## Log
### 2026-10-06 — COMPLETE (batch AUTH-02/05)
- `app/db/seed.py`: نقش‌ها طبق ADR-004، ثابت `PERMISSIONS` (۱۵ کلید `<module>:<action>`)، `ROLE_PERMISSIONS` (customer هیچ؛ support: `orders:read`, `customers:read`؛ content_manager: `content:manage`؛ admin: همه به‌جز `pricing_settings:update`, `users:manage`, `users:manage_roles`, `audit:read`؛ super_admin: همه). `seed_rbac` فقط upsert/insert می‌کند و چیزی را حذف نمی‌کند.
- تست‌ها: `tests/test_seed.py` (unit) و سه تست integration در `tests/test_database.py`.
- دیتابیس توسعه: ردیف `warehouse_manager` (بدون ارجاع در `user_roles`) با تأیید کاربر یک‌بار حذف شد و seed اجرا شد.
- یافته: migration `20260913_0001` خودش `warehouse_manager` را insert می‌کند، پس هر دیتابیس تازه (test، CI، production) آن را دارد. پاک‌کردن همگانی آن یک data migration جدید می‌خواهد که خارج از plan است و به کاربر گزارش شد.
- Validation: pytest 409 passed، ruff، format و mypy سبز.
