# INF-03 — Pagination & filter/sort allowlist

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** FND-02

## Objective
dependency و schema مشترک برای pagination با سقف اندازه صفحه، و الگوی allowlist برای sort و filter.

## PRD reference
«دسته‌بندی محصولات» ✓ («فیلترها و sort باید allowlist داشته باشند»، «page و limit باید محدود شوند»)

## Acceptance Criteria
- [x] سبک pagination در گام plan تأیید شده است. چون PRD `page`/`limit` و total را الزامی می‌داند، page/limit همه‌جا استفاده شد: سقف limit برای public ۴۸ و برای admin ۱۰۰، و page حداکثر ۱۰۰۰.
- [x] limit یا page خارج از محدوده، sort یا query param خارج از allowlist → 400 `VALIDATION_ERROR` با فرمت خطای استاندارد (ADR-011). cursor حذف شد (N/A).
- [x] schema پاسخ: `Page[T]` با فیلدهای `items`، `total`، `page`، `limit` و `pages`.

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
- 2026-09-29: COMPLETE. PRD («دسته‌بندی محصولات» ✓) صفحه‌بندی page/limit به‌همراه «تعداد کل» می‌خواهد، پس cursor کنار گذاشته شد. `BadRequestError` (400) اضافه شد. helper کوئری DB (count + offset) و تست DB به CAT-07 منتقل شد. اعتبارسنجی: pytest 268 passed با دیتابیس تست؛ ruff، format و mypy سبز.
- 2026-09-29: از `tasks/M1-03-pagination-allowlist.md` منتقل شد.
