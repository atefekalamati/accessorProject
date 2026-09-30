# SEC-05 — Secret scanning in CI (gitleaks)

**Status:** NOT_STARTED · **Priority:** HIGH · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** FND-07 · **Level:** MEDIUM

## Objective
جلوگیری از ورود secret به repo با اسکن خودکار gitleaks در CI، قبل از اینکه taskهای auth (AUTH-06 به بعد) token و secret واقعی وارد کد کنند. اولین task فاز ۲.

## PRD reference
«هویت و دسترسی» ✓ (امنیت token و secret)؛ CLAUDE.md بخش ۸ (secretها فقط در `.env`).

## Acceptance Criteria
- [ ] یک step یا job در `.github/workflows/ci.yml` gitleaks را روی push و PR اجرا می‌کند.
- [ ] نسخه gitleaks pin شده است (نسخه دقیق، و اگر باینری دانلود شود، checksum). `latest` ممنوع است.
- [ ] هر finding باعث fail شدن CI می‌شود (exit code غیرصفر).
- [ ] allowlist در `.gitleaks.toml` فقط fixtureهای ساختگی شناخته‌شده را پوشش می‌دهد: JWT ساختگی در `tests/test_logging.py`، `SECRET` در `tests/test_errors.py` و credentialهای دیتابیس تست. هر مورد دلیل مکتوب دارد. allowlist کلی، مثل کل پوشه `tests/`، ممنوع است.
- [ ] اسکن کل تاریخچه شاخه فعلی بدون finding پاس می‌شود.
- [ ] تست منفی: یک secret ساختگی روی شاخه موقت باعث fail شدن CI می‌شود. commit و شاخه موقت بعد از تست حذف می‌شوند و شاهد آن در Log ثبت می‌شود.
- [ ] نحوه اجرای محلی (اختیاری) در README یا `docs/` مستند شده است.

## Implementation Notes
`.github/workflows/ci.yml` (موجود) و `.gitleaks.toml` (جدید). انتخاب بین `gitleaks/gitleaks-action` و دانلود مستقیم باینری در plan همین task انجام می‌شود. نکته: action برای repo متعلق به organization، license لازم دارد. dependency پایتونی جدید ندارد.

## Validation
```powershell
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy app tests
```
به‌علاوه: اجرای سبز CI روی commit نهایی و اجرای قرمز روی commit تست منفی.

## Log
- 2026-09-30: به درخواست کاربر، به‌عنوان اولین task فاز ۲ و پیش‌نیاز AUTH-06 اضافه شد.
