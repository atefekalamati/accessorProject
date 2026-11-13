# OPS-00 — Rewrite monitoring & incidents requirements

**Status:** COMPLETE · **Priority:** MEDIUM · **Estimate:** 1h (estimate) · **Deadline:** — · **Dependencies:** — · **Level:** HIGH

## Objective
بازنویسی بخش قالبی «پایش و رخدادها».

## PRD reference
«پایش و رخدادها» (قالبی).

## Acceptance Criteria
- [x] بخش بازنویسی و ✓ شد.
- [x] ردیف PRD changes.
- [x] تأیید کاربر.

## Implementation Notes
همراه با SEC-00 در یک پیش‌نویس.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-11-13: بازنویسی «پایش و رخدادها» ✓: log، متریک با METRICS_TOKEN، ErrorReporter با log-only، قواعد هشدار، پشتیبان؛ endpointهای قالبی حذف شدند (ADR-060). COMPLETE.
