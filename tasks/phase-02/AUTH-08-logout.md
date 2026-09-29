# AUTH-08 — POST /api/v1/auth/logout

**Status:** NOT_STARTED · **Priority:** MEDIUM · **Estimate:** 1.5h (estimate) · **Deadline:** — · **Dependencies:** AUTH-07, ADR-012 · **Level:** HIGH

## Objective
خروج از حساب و باطل‌کردن session.

## PRD reference
«هویت و دسترسی» ✓

## Acceptance Criteria
- [ ] logout، session جاری را `revoked` می‌کند و cookie refresh را با همان Path پاک می‌کند.
- [ ] refresh بعد از logout → 401.
- [ ] logout تکراری idempotent است و خطا نمی‌دهد.

## Implementation Notes
`app/modules/auth/`.

## Validation
```powershell
python -m pytest   # با TEST_DATABASE_URL
```

## Log
