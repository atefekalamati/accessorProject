# ADM-07 — Role × endpoint matrix tests (5 roles)

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 4h (estimate) · **Deadline:** — · **Dependencies:** ADM-01…06, ADM-08 · **Level:** MEDIUM

## Objective
ماتریس ۵ نقش × همه routeهای `/admin/*`.

## PRD reference
«هویت و دسترسی» ✓.

## Acceptance Criteria
- [x] همه routeهای `/admin/*` از router کشف می‌شوند (route جدید بدون ردیف ماتریس → fail).
- [x] هر نقش فقط مجوزهای seed را دارد؛ بقیه 403؛ بدون token 401.

## Implementation Notes
`tests/test_admin_role_matrix.py`.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-10-27: پیاده‌سازی (batch 5).
  - `tests/test_admin_role_matrix.py`: ماتریس صریح ۵۴ route `/admin` → مجوزهای پذیرفته (any-of)؛ کشف route از OpenAPI، route بدون ردیف → fail.
  - نگاشت نقش‌ها مستقل از seed نوشته و با `ROLE_PERMISSIONS` و ردیف‌های `role_permissions` دیتابیس مقایسه شد.
  - برای هر route: بدون token → 401؛ نقش بدون مجوز → 403 `FORBIDDEN`؛ نقش با مجوز → نه 401 و نه 403 (id تصادفی و بدنه خالی، بدون اثر جانبی). ۳۲۴ درخواست.
  - هیچ نشتی پیدا نشد. Level MEDIUM. COMPLETE.
