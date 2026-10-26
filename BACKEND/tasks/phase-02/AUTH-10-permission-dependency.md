# AUTH-10 — Permission-check dependency

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** AUTH-06, AUTH-02 · **Level:** HIGH

## Objective
`get_current_user` و `require_permission("pricing:update")` به‌عنوان dependencyهای FastAPI، تا همه ماژول‌های بعدی از آن‌ها استفاده کنند.

## PRD reference
«هویت و دسترسی» ✓

## Acceptance Criteria
- [x] بدون توکن یا با توکن نامعتبر → 401. بدون permission لازم → 403.
- [x] permissionها از دیتابیس خوانده می‌شوند، پس تغییر نقش بلافاصله اثر می‌کند. از claim داخل توکن یا ورودی کلاینت اعتماد نمی‌شود.
- [x] کاربر `inactive` یا `blocked` حتی با توکن معتبر → 403. وضعیت فعال‌بودن (و soft delete) در **هر درخواست** از دیتابیس خوانده می‌شود، نه از token (ADR-017).
- [x] helper بررسی مالکیت (`ensure_owner`) برای استفاده در سفارش، سبد و آدرس تعریف شده است.
- [x] تست با routeهای مخصوص تست.

## Implementation Notes
`app/modules/auth/dependencies.py`.

## Validation
```powershell
python -m pytest   # با TEST_DATABASE_URL
python -m mypy app tests
```

## Log
### 2026-10-06 — COMPLETE (batch AUTH-08/10/09)
- `app/modules/auth/dependencies.py`: `get_current_user` (Bearer؛ بدون header یا با scheme غلط → 401)، `require_permission(key)` (کلید ناشناخته → `ValueError` هنگام import؛ نبود permission → 403)، و `ensure_owner` (→ 404 `NOT_FOUND`).
- `AccessService.authenticate` در `service.py`: JWT decode می‌شود، سپس در یک transaction کوتاه (تا serviceها بتوانند روی همان session دوباره `begin()` کنند) user، session، roles و permissions از DB خوانده می‌شوند. user ناموجود یا soft-deleted و session revoke‌شده یا منقضی → 401. inactive یا blocked → 403 (ADR-018).
- `CurrentUser` (frozen dataclass): `id`، `session_id`، `status`، `roles`، `permissions`.
- تست‌ها: `tests/test_auth_permissions.py` (۲۸ مورد با routeهای مخصوص تست: ماتریس ۵ نقش × ۱۵ permission، token دستکاری‌شده/منقضی/`typ` غلط/secret دیگر/`alg=none`/session ناشناخته، logout و rotation، session منقضی، حذف‌شده، inactive و blocked، تغییر فوری نقش، اجتماع نقش‌ها، claim و هدر جعلی، transaction بعد از auth) و `tests/test_auth_dependencies.py` (۸ unit test).
- Validation: pytest 511 passed، ruff، format و mypy سبز.
