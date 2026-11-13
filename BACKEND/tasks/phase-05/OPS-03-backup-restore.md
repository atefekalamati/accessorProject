# OPS-03 — Backup/restore runbook

**Status:** NOT_STARTED · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** — · **Level:** HIGH

## Objective
runbook پشتیبان‌گیری و بازیابی PostgreSQL، با تمرین بازیابی.

## PRD reference
«معماری سیستم» ✓.

## Acceptance Criteria
- [ ] runbook با دستورات دقیق.
- [ ] بازیابی روی دیتابیس یک‌بارمصرف تمرین و نتیجه ثبت شد.
- [ ] هیچ volume یا دیتابیس واقعی دست نخورد.

## Implementation Notes
فقط روی کانتینر یک‌بارمصرف؛ `atk_postgres_data` دست نمی‌خورد.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
