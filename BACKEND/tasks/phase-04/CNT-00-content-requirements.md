# CNT-00 — Rewrite content requirements

**Status:** COMPLETE · **Priority:** MEDIUM · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** — · **Level:** HIGH

## Objective
بازنویسی «محتوا و بنرها»، «درباره برند»، «تماس با ما»، «سؤالات متداول» و «قوانین و حریم خصوصی»، و تکمیل «صفحه اصلی» ✓.

## PRD reference
همان بخش‌ها؛ D36، D40، D41، D42 (ADR-053).

## Acceptance Criteria
- [x] بخش‌ها بازنویسی و ✓ شدند؛ CRUDهای قالبی حذف شدند.
- [x] ردیف جدول PRD changes و تصمیم‌ها در DECISIONS.md (ADR-053).
- [x] تأیید کاربر (2026-10-26).

## Implementation Notes
فقط PRD و DECISIONS.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-10-26: پیش‌نویس مشترک ACC-00، ADM-00 و CNT-00 (بدون ویرایش PRD) به‌همراه هفت سؤال فرستاده شد. کاربر با افزوده‌ها تأیید کرد: ADM-08، ماسک موبایل و audit مشاهده، و طراحی E (نمونه رنگ و `is_new` → CAT-18). PRD ویرایش شد و D35–D42 در ADR-053 ثبت شد. COMPLETE.
