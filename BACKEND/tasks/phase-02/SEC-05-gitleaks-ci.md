# SEC-05 — Secret scanning in CI (gitleaks)

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** FND-07 · **Level:** MEDIUM

## Objective
جلوگیری از ورود secret به repo با اسکن خودکار gitleaks در CI، قبل از اینکه taskهای auth (AUTH-06 به بعد) token و secret واقعی وارد کد کنند. اولین task فاز ۲.

## PRD reference
«هویت و دسترسی» ✓ (امنیت token و secret)؛ CLAUDE.md بخش ۸ (secretها فقط در `.env`).

## Acceptance Criteria
- [x] یک step یا job در `.github/workflows/ci.yml` gitleaks را روی push و PR اجرا می‌کند.
- [x] نسخه gitleaks pin شده است (نسخه دقیق، و اگر باینری دانلود شود، checksum). `latest` ممنوع است.
- [x] هر finding باعث fail شدن CI می‌شود (exit code غیرصفر).
- [x] allowlist در `.gitleaks.toml` فقط fixtureهای ساختگی شناخته‌شده را پوشش می‌دهد: JWT ساختگی در `tests/test_logging.py`، `SECRET` در `tests/test_errors.py` و credentialهای دیتابیس تست. هر مورد دلیل مکتوب دارد. allowlist کلی، مثل کل پوشه `tests/`، ممنوع است.
- [x] اسکن کل تاریخچه شاخه فعلی بدون finding پاس می‌شود.
- [x] تست منفی: یک secret ساختگی روی شاخه موقت باعث fail شدن CI می‌شود. commit و شاخه موقت بعد از تست حذف می‌شوند و شاهد آن در Log ثبت می‌شود.
- [x] نحوه اجرای محلی (اختیاری) در README یا `docs/` مستند شده است.

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
- 2026-10-06: COMPLETE.
  - روش: دانلود مستقیم باینری gitleaks `8.30.1` (linux_x64) با sha256 `551f6fc8…f2470eb` که با فایل checksums رسمی release تطبیق داده شد. job جدا به اسم `secret-scan` با `fetch-depth: 0` و `--redact --exit-code 1`.
  - اسکن کل تاریخچه (24 commit، image `ghcr.io/gitleaks/gitleaks:v8.30.1`): no leaks found. هیچ‌کدام از fixtureهای شناخته‌شده (JWT در test_logging، `SECRET` در test_errors، `postgres:test`، `JWT_SECRET` در conftest) با قوانین پیش‌فرض فلگ نشد، پس allowlist خالی ماند. بررسی این fixtureها در `.gitleaks.toml` مستند شده است.
  - تست منفی (به دستور کاربر فقط محلی): شاخه موقت `tmp/sec-05-negative` با commit `ead387e` (GitHub PAT ساختگی و تصادفی) ساخته شد. اسکن با image pin‌شده: `leaks found: 1`، rule `github-pat`، exit code 1. شاخه بدون push حذف شد و `git ls-remote` هیچ شاخه `tmp/*` نشان نداد.
  - اسکن `dir` روی working tree: 24 finding، همه در فایل‌های untracked (`.env` که gitignored است و پکیج‌های `.venv`). هیچ‌کدام در فایل tracked نیست.
  - pytest 345 passed (postgres-test)؛ ruff، format و mypy سبز.
- 2026-09-30: به درخواست کاربر، به‌عنوان اولین task فاز ۲ و پیش‌نیاز AUTH-06 اضافه شد.
