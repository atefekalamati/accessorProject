# AUTH-02 — Base roles & permissions seed

**Status:** NOT_STARTED · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** FND-05, ADR-004 · **Level:** HIGH

## Objective
جدول‌های `roles`، `permissions`، `user_roles` و `role_permissions` از قبل موجودند. این task مجموعه نهایی نقش‌ها و کلیدهای permission را seed می‌کند.

## PRD reference
«هویت و دسترسی» ✓. نقش‌های اضافه در «قیمت و مالیات» ✓، «موجودی و رزرو» ✓، «صفحه اصلی» ✓ و «دسته‌بندی محصولات» ✓ آمده‌اند.

## Acceptance Criteria
- [ ] نقش‌ها دقیقاً طبق ADR-004: `customer`، `support`، `content_manager`، `admin`، `super_admin`. Guest نقش دیتابیسی نیست.
- [ ] `warehouse_manager` از `DEFAULT_ROLES` حذف شد. اگر ردیف آن در دیتابیس توسعه مانده، حذف آن فقط با تأیید کاربر است.
- [ ] کلیدهای permission به شکل `<module>:<action>` هستند (مثلاً `pricing:update`، `inventory:update`، `users:manage_roles`) و در یک ثابت کد تعریف شده‌اند.
- [ ] `role_permissions` برای هر نقش seed شده و `super_admin` همه permissionها را دارد.
- [ ] seed idempotent است و نقش‌ها و permissionهای حذف‌شده از فهرست را پاک نمی‌کند، فقط upsert می‌کند.
- [ ] تست seed به‌روز شده است.

## Implementation Notes
`app/db/seed.py`، `tests/test_database.py`.

## Validation
```powershell
python -m app.db.seed
python -m pytest   # با TEST_DATABASE_URL
python -m mypy app tests
```

## Log
