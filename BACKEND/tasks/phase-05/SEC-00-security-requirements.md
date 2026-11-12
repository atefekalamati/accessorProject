# SEC-00 — Rewrite security & acceptance requirements

**Status:** NOT_STARTED · **Priority:** HIGH · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** — · **Level:** HIGH

## Objective
بازنویسی بخش‌های قالبی «امنیت»، «تست و پذیرش» و «حالت‌های رابط» با الزامات دقیق و قابل تست.

## PRD reference
«امنیت»، «تست و پذیرش»، «حالت‌های رابط» (قالبی).

## Acceptance Criteria
- [ ] بخش‌ها بازنویسی و ✓ شدند؛ CRUDهای قالبی حذف شدند.
- [ ] ردیف PRD changes و تصمیم‌ها در DECISIONS.md.
- [ ] تأیید کاربر (تغییر PRD: استثنای AUTOPILOT).

## Implementation Notes
فقط PRD و DECISIONS؛ همراه با OPS-00 در یک پیش‌نویس فرستاده می‌شود.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
