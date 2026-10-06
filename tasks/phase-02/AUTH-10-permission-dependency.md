# AUTH-10 — Permission-check dependency

**Status:** NOT_STARTED · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** AUTH-06, AUTH-02 · **Level:** HIGH

## Objective
`get_current_user` و `require_permission("pricing:update")` به‌عنوان dependencyهای FastAPI، تا همه ماژول‌های بعدی از آن‌ها استفاده کنند.

## PRD reference
«هویت و دسترسی» ✓

## Acceptance Criteria
- [ ] بدون توکن یا با توکن نامعتبر → 401. بدون permission لازم → 403.
- [ ] permissionها از دیتابیس خوانده می‌شوند، پس تغییر نقش بلافاصله اثر می‌کند. از claim داخل توکن یا ورودی کلاینت اعتماد نمی‌شود.
- [ ] کاربر `inactive` یا `blocked` حتی با توکن معتبر → 403. وضعیت فعال‌بودن (و soft delete) در **هر درخواست** از دیتابیس خوانده می‌شود، نه از token (ADR-017).
- [ ] helper بررسی مالکیت (`ensure_owner`) برای استفاده در سفارش، سبد و آدرس تعریف شده است.
- [ ] تست با routeهای مخصوص تست.

## Implementation Notes
`app/modules/auth/dependencies.py`.

## Validation
```powershell
python -m pytest   # با TEST_DATABASE_URL
python -m mypy app tests
```

## Log
