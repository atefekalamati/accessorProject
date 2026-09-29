# INF-02 — Integer-Toman money utilities

**Status:** COMPLETE (2026-09-29) · **Priority:** HIGH · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** D14 (resolved، ADR-001)، D18 (ADR-014) · **Level:** MEDIUM

## Objective
یک نوع و helper واحد برای مبلغ: عدد صحیح تومان، بدون float، و تابع گردکردن که فقط pricing service از آن استفاده می‌کند.

## PRD reference
«قیمت و مالیات» ✓

## Acceptance Criteria
- [x] مبلغ همیشه `int` تومان است. نوع `Toman` در سطح schema مقدارهای bool، str (حتی `"1500"`)، float و منفی را رد می‌کند. (پاسخ HTTP 400 برای آن در INF-01 است.)
- [x] تابع خالص `round_amount(amount, mode, step)` برای هر سه mode (`up`، `down`، `nearest` half-up؛ ADR-014) تست جدولی دارد. پیش‌فرض `nearest` با `step=1`.
- [x] الگوی ستون مشخص است: `BigInteger` همراه `non_negative_check(column)` (CheckConstraint `>= 0`)، و در docstring مستند شده است.
- [x] هیچ‌جا از `float` برای پول استفاده نشده است؛ `round_amount` ورودی float را با `TypeError` رد می‌کند و محاسبه میانی با `Fraction` دقیق است.

## Implementation Notes
`app/shared/money.py` و `tests/test_money.py` (هر دو فایل جدید و برنامه‌ریزی‌شده).

## Validation
```powershell
python -m pytest tests/test_money.py
python -m ruff check .
python -m ruff format --check .
python -m mypy app tests
```

## Log
- 2026-09-29: از `tasks/M1-02-money-utils.md` منتقل شد. D14 با ADR-001 به تومان حل شد.
- 2026-09-29: پیاده‌سازی شد: `app/shared/money.py` و `tests/test_money.py` (۴۸ تست). modeها طبق تصمیم کاربر (ADR-014). معیار 400 به INF-01 منتقل شد. اعتبارسنجی: pytest کامل با دیتابیس تست، ruff، format و mypy سبز.
