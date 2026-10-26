# ADM-07 — Role × endpoint matrix tests (5 roles)

**Status:** NOT_STARTED · **Priority:** HIGH · **Estimate:** 4h (estimate) · **Deadline:** — · **Dependencies:** ADM-01…06, ADM-08 · **Level:** MEDIUM

## Objective
ماتریس ۵ نقش × همه routeهای `/admin/*`.

## PRD reference
«هویت و دسترسی» ✓.

## Acceptance Criteria
- [ ] همه routeهای `/admin/*` از router کشف می‌شوند (route جدید بدون ردیف ماتریس → fail).
- [ ] هر نقش فقط مجوزهای seed را دارد؛ بقیه 403؛ بدون token 401.

## Implementation Notes
`tests/test_admin_role_matrix.py`.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log

