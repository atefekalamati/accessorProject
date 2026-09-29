# INF-03 — Pagination & filter/sort allowlist

**Status:** NOT_STARTED · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** FND-02

## Objective
dependency و schema مشترک برای pagination با سقف اندازه صفحه، و الگوی allowlist برای sort و filter.

## PRD reference
«دسته‌بندی محصولات» ✓ («فیلترها و sort باید allowlist داشته باشند»، «page و limit باید محدود شوند»)

## Acceptance Criteria
- [ ] سبک pagination در گام plan تأیید شده است. پیشنهاد: cursor opaque برای لیست‌های عمومی (سقف 48) و page/limit برای admin.
- [ ] limit بیش از سقف، cursor خراب یا sort/filter خارج از allowlist → 400 با فرمت خطای استاندارد (ADR-011).
- [ ] schema پاسخ عمومی: `items` و `next_cursor` (یا `total` برای page/limit).

## Implementation Notes
`app/shared/pagination.py` و `tests/test_pagination.py` (هر دو فایل جدید و برنامه‌ریزی‌شده).

## Validation
```powershell
python -m pytest tests/test_pagination.py
python -m ruff check .
python -m ruff format --check .
python -m mypy app tests
```

## Log
- 2026-09-29: از `tasks/M1-03-pagination-allowlist.md` منتقل شد.
