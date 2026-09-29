# AUTH-07 — POST /api/v1/auth/refresh with rotation

**Status:** NOT_STARTED · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** AUTH-06, ADR-012

## Objective
صدور access token جدید با refresh token معتبر، و چرخش (rotation) refresh token.

## PRD reference
«هویت و دسترسی» ✓

## Acceptance Criteria
- [ ] refresh token فقط از cookie خوانده می‌شود (ADR-012). نبود cookie، یا refresh منقضی، باطل یا ناشناخته → 401.
- [ ] rotation انجام می‌شود: session قبلی باطل و refresh جدید در همان `family_id` صادر می‌شود.
- [ ] استفاده دوباره از refresh باطل‌شده، کل family را باطل می‌کند (reuse detection).
- [ ] کاربر غیرفعال یا مسدود توکن جدید نمی‌گیرد.

## Implementation Notes
`app/modules/auth/`.

## Validation
```powershell
python -m pytest   # با TEST_DATABASE_URL
python -m mypy app tests
```

## Log
