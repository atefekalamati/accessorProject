# SEC-06 — Dependency lock file with hashes

**Status:** NOT_STARTED · **Priority:** MEDIUM · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** FND-07, FND-03 · **Level:** MEDIUM

## Objective
نصب قابل‌تکرار و امن dependencyها: یک lock file با نسخه دقیق و hash برای همه dependencyها (مستقیم و غیرمستقیم)، تا CI و image Docker دقیقاً همان پکیج‌ها را نصب کنند و پکیج دستکاری‌شده رد شود. `pyproject.toml` همچنان بازه‌ها را نگه می‌دارد (تصمیم کاربر: range pin).

## PRD reference
— (زیرساخت و امنیت زنجیره تأمین). درخواست کاربر در 2026-10-09: در اولین batch بدون task HIGH اجرا شود.

## Acceptance Criteria
- [ ] lock file برای runtime و یک lock جدا برای dev (شامل runtime) با `--hash` برای هر پکیج، تولیدشده از `pyproject.toml`.
- [ ] CI (`.github/workflows/ci.yml`) با `pip install --require-hashes -r <dev lock>` نصب می‌کند و سپس پروژه را با `--no-deps` نصب می‌کند.
- [ ] `Dockerfile` با `--require-hashes` از lock runtime نصب می‌کند و سپس `pip install --no-deps .`.
- [ ] اگر `pyproject.toml` با lock هماهنگ نباشد، CI fail می‌شود (بررسی drift).
- [ ] دستور بازتولید lock در CLAUDE.md بخش ۵ و این فایل ثبت می‌شود.
- [ ] build Docker و CI سبز؛ pytest، ruff و mypy سبز.

## Implementation Notes
- ابزار در گام plan انتخاب می‌شود. گزینه‌ها: `pip-tools` (`pip-compile --generate-hashes`) یا `uv pip compile --generate-hashes`. هر دو یک dependency جدید برای dev هستند و دلیل آن باید در plan ذکر شود.
- lock برای Linux/Python 3.12 (CI و Docker) تولید می‌شود. اگر hashها با wheelهای Windows محلی فرق داشتند، در plan تصمیم بگیر (مثلاً نصب محلی همچنان با `pip install -e ".[dev]"`).
- نام فایل‌ها پیشنهادی: `requirements.lock` و `requirements-dev.lock` در ریشه repo.

## Validation
```powershell
python -m pytest   # با TEST_DATABASE_URL
docker compose build api
```

## Log
