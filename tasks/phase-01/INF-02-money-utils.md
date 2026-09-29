# INF-02 — Integer-Toman money utilities

**Status:** NOT_STARTED · **Priority:** HIGH · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** D14 (resolved، ADR-001)

## Objective
یک نوع و helper واحد برای مبلغ: عدد صحیح تومان، بدون float، و تابع گردکردن که فقط pricing service از آن استفاده می‌کند.

## PRD reference
«قیمت و مالیات» ✓

## Acceptance Criteria
- [ ] مبلغ همیشه `int` تومان است. ورودی float یا رشته اعشاری با 400 (validation، ADR-011) رد می‌شود. مبلغ منفی رد می‌شود.
- [ ] تابع خالص `round_amount(amount, mode, step)` برای همه modeهای پشتیبانی‌شده تست جدولی دارد.
- [ ] الگوی ستون مشخص است: `BigInteger` همراه CheckConstraint `>= 0`، و در docstring مستند شده است.
- [ ] هیچ‌جا از `float` برای پول استفاده نشده است.

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
