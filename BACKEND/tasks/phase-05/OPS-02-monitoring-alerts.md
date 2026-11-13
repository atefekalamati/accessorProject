# OPS-02 — Monitoring & alerts

**Status:** COMPLETE · **Priority:** MEDIUM · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** OPS-01 · **Level:** MEDIUM

## Objective
تعریف هشدارها روی متریک‌ها.

## PRD reference
«پایش و رخدادها» ✓ (بعد از OPS-00).

## Acceptance Criteria
- [x] هشدارها با آستانه و runbook کوتاه تعریف شدند.

## Implementation Notes
جزئیات بعد از تأیید OPS-00.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-11-13: قواعد هشدار Prometheus در ops/prometheus/alerts.yml (نرخ 5xx، 503 درگاه، توقف job تطبیق و sweep، refund_required باز بیش از ۲۴ ساعت، database_up، شکست scrape) با runbook هر هشدار در docs/ops/ALERTS.md؛ تست که هر قاعده severity و runbook دارد، هیچ بخش runbook بی‌قاعده نیست و فقط متریک‌ها و jobهایی را به کار می‌برد که API واقعاً منتشر می‌کند؛ اجرای واقعی به D13 بستگی دارد. COMPLETE.
