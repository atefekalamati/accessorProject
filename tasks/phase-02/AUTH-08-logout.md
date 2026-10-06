# AUTH-08 — POST /api/v1/auth/logout

**Status:** COMPLETE · **Priority:** MEDIUM · **Estimate:** 1.5h (estimate) · **Deadline:** — · **Dependencies:** AUTH-07, ADR-012 · **Level:** HIGH

## Objective
خروج از حساب و باطل‌کردن session.

## PRD reference
«هویت و دسترسی» ✓

## Acceptance Criteria
- [x] logout، session جاری را `revoked` می‌کند و cookie refresh را با همان Path پاک می‌کند.
- [x] refresh بعد از logout → 401.
- [x] logout تکراری idempotent است و خطا نمی‌دهد.

## Implementation Notes
`app/modules/auth/`.

## Validation
```powershell
python -m pytest   # با TEST_DATABASE_URL
```

## Log
### 2026-10-06 — COMPLETE (batch AUTH-08/10/09)
- `POST /api/v1/auth/logout` → 204: refresh فقط از cookie خوانده می‌شود و access لازم نیست. `AuthService.logout` session را با `FOR UPDATE` قفل می‌کند و sessionهای فعال همان family را revoke می‌کند (که بعد از rotation همان session جاری است؛ ADR-017). audit `auth.logout` با `session_id` و `family_id` ثبت می‌شود.
- idempotent: اگر cookie نباشد، ناشناخته باشد یا قبلاً revoke شده باشد، باز هم 204 است و cookie پاک می‌شود. در این حالت audit ثبت نمی‌شود و reuse detection اجرا نمی‌شود.
- cookie با همان `Path=/api/v1/auth; Secure; HttpOnly; SameSite=Strict` و `Max-Age=0` پاک می‌شود، به‌علاوه `Cache-Control: no-store`. sessionهای دستگاه‌های دیگر دست نمی‌خورند.
- ابطال فوری access token بعد از logout در AUTH-10 انجام می‌شود (چک `sid` در هر درخواست).
- تست‌ها: `tests/test_auth_logout.py` (۸ مورد).
- Validation: pytest 479 passed، ruff، format و mypy سبز.
