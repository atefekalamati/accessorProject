# CAT-12 — Catalog API tests

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** CAT-06…CAT-11, CAT-07 · **Level:** MEDIUM

## Objective
پوشش کامل خطاهای 400/401/403/404/409/422 برای همه endpointهای کاتالوگ (عمومی و admin) و یک تست end-to-end کاتالوگ: ساخت دسته، محصول، تنوع، موجودی و تصویر، انتشار، سپس دیدن آن در لیست، فیلتر و جزئیات عمومی.

## PRD reference
«دسته‌بندی محصولات» ✓، «جزئیات محصول» ✓، «محصولات» ✓ (خطاهای کلیدی)؛ CLAUDE.md بخش ۷.

## Plan
- فایل `tests/test_catalog_api.py`: یک نقشه «endpoint → کدهای خطای کاربردی» به‌صورت داده. هر خانه یا یک تست موجود را نام می‌برد یا در همین فایل تست می‌شود. فقط خانه‌های خالی تست جدید می‌گیرند (بدون تکرار تست‌های موجود).
- تست سراسری: هر route کاتالوگ در نقشه هست (route جدید بدون ردیف → fail).
- تست end-to-end از طریق API admin با کاربر super_admin.
- ریسک: تست شکننده وابسته به داده دیگر تست‌ها (scope با دسته یکتا).

## Acceptance Criteria
- [x] هر endpoint کاتالوگ برای کدهای مرتبط از 400/401/403/404/409/422 تست دارد (یا «نامرتبط» با دلیل در نقشه).
- [x] تست سراسری نقشه را با routeهای واقعی تطبیق می‌دهد.
- [x] یک تست end-to-end کاتالوگ سبز است.
- [x] pytest، ruff، format و mypy سبز.

## Implementation Notes
- `tests/test_catalog_api.py`: نقشه `COVERAGE` (۲۲ endpoint × ۶ کد = ۱۳۲ خانه)؛ هر خانه یک تست موجود (`module::test`) یا `n/a: <دلیل>` است. نگهبان‌ها: نقشه = routeهای واقعی (از OpenAPI) و هر تست نام‌برده وجود دارد (AST).
- خانه‌های خالی که اینجا تست شدند: id غیر UUID در مسیر → 400 برای ۱۳ ترکیب admin (شامل سه DELETE)؛ پارامتر ناشناخته در `GET /categories/{slug}` → 400.
- end-to-end: super_admin از API دسته، فیلترها، محصول، دو تنوع با قیمت و تصویر می‌سازد (موجودی مستقیم در DB تا INV-02)، منتشر می‌کند، سپس لیست، فیلتر، `/filters` و جزئیات عمومی را بررسی می‌کند و بعد از archive محصول پنهان می‌شود.
- fixtureهای `Account`/`make_account` از `test_admin_products.py` به `conftest.py` منتقل شدند. teardown `catalog` رسانه‌های آپلودشده را هم حذف می‌کند.
- **Rollback:** فقط تست؛ `git revert`.

## Validation
```powershell
python -m pytest -q   # با TEST_DATABASE_URL
python -m ruff check .; python -m ruff format --check .; python -m mypy app tests
```

## Log
- 2026-10-11: plan (batch CAT-07/CAT-12).
- 2026-10-11: پیاده‌سازی؛ 40 تست جدید. pytest (1223 passed)، ruff، format و mypy سبز. M2.2 کامل شد. COMPLETE.
