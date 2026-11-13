# OPS-03 — Backup/restore runbook

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** — · **Level:** HIGH

## Objective
runbook پشتیبان‌گیری و بازیابی PostgreSQL، با تمرین بازیابی.

## PRD reference
«معماری سیستم» ✓.

## Acceptance Criteria
- [x] runbook با دستورات دقیق.
- [x] بازیابی روی دیتابیس یک‌بارمصرف تمرین و نتیجه ثبت شد.
- [x] هیچ volume یا دیتابیس واقعی دست نخورد.

## Implementation Notes
فقط روی کانتینر یک‌بارمصرف؛ `atk_postgres_data` دست نمی‌خورد.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-11-13: پشتیبان و بازیابی: scripts/backup.sh (pg_dump custom، فایل 600 در backups/ gitignored، بررسی با pg_restore --list، retention ۱۴ روزه فقط برای فایل‌های خودش با timestamp دقیق، رد دیتابیس _test بدون --allow-test)، runbook در docs/ops/BACKUP-RESTORE.md، و scripts/restore_rehearsal.sh فقط روی postgres-test؛ تمرین سبز: ۴۸ جدول با تعداد ردیف برابر، revision یکسان 20261113_0033، سه trigger جدول audit_logs برگشتند؛ atk_postgres_data دست نخورد؛ بازبین مستقل plan و diff را تأیید کرد (یک major و چند minor رفع شد)؛ بدون تغییر کد Python (suite کامل روی همین کد: ۲۳۲۶ سبز). COMPLETE.
