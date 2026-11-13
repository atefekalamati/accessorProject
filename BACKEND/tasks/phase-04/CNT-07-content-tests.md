# CNT-07 — Content tests

**Status:** COMPLETE · **Priority:** MEDIUM · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** CNT-01…06 · **Level:** LOW

## Objective
پوشش تفکیک عمومی و ادمین محتوا و بستن شکاف‌های باقی‌مانده.

## PRD reference
«صفحه اصلی» ✓، «محتوا و بنرها» ✓، «درباره برند» ✓، «تماس با ما» ✓، «سؤالات متداول» ✓، «قوانین و حریم خصوصی» ✓.

## Acceptance Criteria
- [x] خروجی عمومی هیچ فیلد داخلی (`created_by`، `updated_by`، `deleted_at`، پیش‌نویس) ندارد.
- [x] همه route‌های ادمین محتوا در ماتریس نقش‌ها هستند.
- [x] تأیید شکاف‌ها در برابر معیارهای پذیرش PRD همین بخش‌ها.

## Implementation Notes
`tests/`.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-11-13: تست end-to-end تفکیک عمومی و ادمین: content_manager صفحه، FAQ، بنر و همه نوع سکشن را از API می‌سازد و مهمان بدون ورود فقط منتشرشده‌ها را بدون هیچ فیلد داخلی می‌بیند؛ پیش‌نویس 404؛ محصول ناموجود بدون خرید سریع؛ route‌های عمومی بدون ورود؛ همه route‌های ادمین محتوا در ماتریس نقش‌ها (ADM-07). COMPLETE.
