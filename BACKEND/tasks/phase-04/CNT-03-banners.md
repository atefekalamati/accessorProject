# CNT-03 — Banner model + admin

**Status:** COMPLETE · **Priority:** MEDIUM · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** CNT-00, CAT-05, CNT-01 · **Level:** MEDIUM

## Objective
بنر زمان‌بندی‌شده با CRUD ادمین و نمایش در `GET /home`.

## PRD reference
«محتوا و بنرها» ✓؛ ADR-028، D36، D41 (ADR-053).

## Acceptance Criteria
- [x] جدول `banners` با migration جدید؛ تصویر دسکتاپ و موبایل از Media.
- [x] بازه `[starts_at, ends_at)` رعایت می‌شود (قبل، داخل، بعد).
- [x] مقصد فقط داخلی؛ لینک بیرونی → 400؛ مقصد یا رسانه ناموجود → 404؛ غیرقابل‌انتشار → 422.
- [x] بنری که مقصدش دیگر عمومی نیست در خروجی نمی‌آید.
- [x] URL تصویر ساخته‌شده سرور؛ حذف نرم؛ هر تغییر در AuditLog؛ customer → 403.

## Implementation Notes
`app/modules/content/`.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-11-12: بنر زمان‌بندی‌شده: CRUD ادمین با content:manage، تصویر دسکتاپ و موبایل از Media (تصویر محصول 422)، مقصد فقط داخلی (400/404/422)، URL ساخته سرور، بازه [starts_at, ends_at)، نمایش در سکشن hero و چیدمان پیش‌فرض GET /home، پنهان شدن بنر با مقصد غیرعمومی، audit؛ migration 0032؛ بررسی مقصد مشترک با سکشن‌ها (references.py). COMPLETE.
