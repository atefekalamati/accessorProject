# CNT-07 — Content tests

**Status:** NOT_STARTED · **Priority:** MEDIUM · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** CNT-01…06 · **Level:** LOW

## Objective
پوشش تفکیک عمومی و ادمین محتوا و بستن شکاف‌های باقی‌مانده.

## PRD reference
«صفحه اصلی» ✓، «محتوا و بنرها» ✓، «درباره برند» ✓، «تماس با ما» ✓، «سؤالات متداول» ✓، «قوانین و حریم خصوصی» ✓.

## Acceptance Criteria
- [ ] خروجی عمومی هیچ فیلد داخلی (`created_by`، `updated_by`، `deleted_at`، پیش‌نویس) ندارد.
- [ ] همه route‌های ادمین محتوا در ماتریس نقش‌ها هستند.
- [ ] تأیید شکاف‌ها در برابر معیارهای پذیرش PRD همین بخش‌ها.

## Implementation Notes
`tests/`.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
