# SEC-01 — Global rate limiting

**Status:** NOT_STARTED · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** SEC-00 · **Level:** HIGH

## Objective
سقف درخواست سراسری برای endpointهای عمومی و حساس طبق SEC-00.

## PRD reference
«امنیت» ✓ (بعد از SEC-00).

## Acceptance Criteria
- [ ] سقف‌ها طبق PRD؛ عبور از سقف → 429 `RATE_LIMITED` با `Retry-After`.
- [ ] پشت proxy به OPS-04 نیاز دارد (DEFERRED)؛ تا آن موقع قابل تنظیم.
- [ ] تست سقف و همزمانی.

## Implementation Notes
جزئیات بعد از تأیید SEC-00.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
