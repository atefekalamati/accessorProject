# ORD-08 — Returns (stock only after inspection)

**Status:** NOT_STARTED · **Priority:** LOW · **Estimate:** 6h (estimate) · **Deadline:** — · **Dependencies:** ORD-07 · **Level:** HIGH

## Objective
پیاده‌سازی مرجوعی طبق ORD-07. بعد از تأیید ORD-07 به ORD-08..ORD-10 شکسته می‌شود.

## PRD reference
«مرجوعی» (بعد از ORD-07 ✓)؛ «موجودی و رزرو» ✓.

## Acceptance Criteria
- [ ] بعد از تأیید ORD-07 تکمیل می‌شود.
- [ ] plan برای تأیید کاربر متوقف می‌شود (دستور کاربر، ADR-062).

## Implementation Notes
—

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
