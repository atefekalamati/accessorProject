# AUTH-07 — POST /api/v1/auth/refresh with rotation

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** AUTH-06, ADR-012 · **Level:** HIGH

## Objective
صدور access token جدید با refresh token معتبر، و چرخش (rotation) refresh token.

## PRD reference
«هویت و دسترسی» ✓

## Acceptance Criteria
- [x] refresh token فقط از cookie خوانده می‌شود (ADR-012). نبود cookie، یا refresh منقضی، باطل یا ناشناخته → 401.
- [x] rotation انجام می‌شود: session قبلی باطل و refresh جدید در همان `family_id` صادر می‌شود.
- [x] استفاده دوباره از refresh باطل‌شده، کل family را باطل می‌کند (reuse detection).
- [x] کاربر غیرفعال یا مسدود توکن جدید نمی‌گیرد.

## Implementation Notes
`app/modules/auth/`.

## Validation
```powershell
python -m pytest   # با TEST_DATABASE_URL
python -m mypy app tests
```

## Log
### 2026-10-06 — COMPLETE (batch AUTH-06/07)
- `POST /api/v1/auth/refresh`: refresh فقط از cookie `refresh_token` خوانده می‌شود (body و هدر `Authorization` نادیده گرفته می‌شوند). `AuthService.refresh` ردیف session را با `FOR UPDATE` قفل می‌کند و rotation در همان `family_id` و با TTL تازه انجام می‌شود.
- reuse: ارائه token revoke‌شده کل family را revoke می‌کند و audit `auth.refresh_reuse` با `family_id` و `revoked_sessions` ثبت می‌شود. grace period ندارد (ADR-017).
- کاربر inactive، blocked یا soft-deleted → 401 و session او revoke می‌شود.
- تست‌ها: `tests/test_auth_refresh.py` (۱۱ مورد: rotation و cookie، نبودن یا ناشناخته‌بودن cookie، token خارج از cookie، reuse و دست‌نخوردن family دیگر، session منقضی، inactive، blocked و حذف‌شده، refresh همزمان).
- Validation: pytest 471 passed، ruff، format و mypy سبز.
