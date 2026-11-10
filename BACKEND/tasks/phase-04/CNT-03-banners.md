# CNT-03 — Banner model + admin

**Status:** NOT_STARTED · **Priority:** MEDIUM · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** CNT-00, CAT-05, CNT-01 · **Level:** MEDIUM

## Objective
بنر زمان‌بندی‌شده با CRUD ادمین و نمایش در `GET /home`.

## PRD reference
«محتوا و بنرها» ✓؛ ADR-028، D36، D41 (ADR-053).

## Acceptance Criteria
- [ ] جدول `banners` با migration جدید؛ تصویر دسکتاپ و موبایل از Media.
- [ ] بازه `[starts_at, ends_at)` رعایت می‌شود (قبل، داخل، بعد).
- [ ] مقصد فقط داخلی؛ لینک بیرونی → 400؛ مقصد یا رسانه ناموجود → 404؛ غیرقابل‌انتشار → 422.
- [ ] بنری که مقصدش دیگر عمومی نیست در خروجی نمی‌آید.
- [ ] URL تصویر ساخته‌شده سرور؛ حذف نرم؛ هر تغییر در AuditLog؛ customer → 403.

## Implementation Notes
`app/modules/content/`.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
