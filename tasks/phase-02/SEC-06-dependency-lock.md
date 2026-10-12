# SEC-06 — Dependency lock file with hashes

**Status:** COMPLETE · **Priority:** MEDIUM · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** FND-07, FND-03 · **Level:** MEDIUM

## Objective
نصب قابل‌تکرار و امن dependencyها: یک lock file با نسخه دقیق و hash برای همه dependencyها (مستقیم و غیرمستقیم)، تا CI و image Docker دقیقاً همان پکیج‌ها را نصب کنند و پکیج دستکاری‌شده رد شود. `pyproject.toml` همچنان بازه‌ها را نگه می‌دارد (تصمیم کاربر: range pin).

## PRD reference
— (زیرساخت و امنیت زنجیره تأمین). درخواست کاربر در 2026-10-09: در اولین batch بدون task HIGH اجرا شود.

## Acceptance Criteria
- [x] lock file برای runtime و یک lock جدا برای dev (شامل runtime) با `--hash` برای هر پکیج، تولیدشده از `pyproject.toml`.
- [x] CI (`.github/workflows/ci.yml`) با `pip install --require-hashes -r <dev lock>` نصب می‌کند و سپس پروژه را با `--no-deps` نصب می‌کند.
- [x] `Dockerfile` با `--require-hashes` از lock runtime نصب می‌کند و سپس `pip install --no-deps .`.
- [x] اگر `pyproject.toml` با lock هماهنگ نباشد، CI fail می‌شود (بررسی drift).
- [x] دستور بازتولید lock در CLAUDE.md بخش ۵ و این فایل ثبت می‌شود.
- [x] build Docker و CI سبز؛ pytest، ruff و mypy سبز.

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
- 2026-10-10: COMPLETE (batch SEC-07/SEC-06/CAT-01..03).
  - ابزار: `uv pip compile --universal --generate-hashes --python-version 3.12` (dependency جدید dev: `uv>=0.13,<0.14`). دلیل: یک lock برای Linux (CI و Docker) و Windows (محلی) با markerهای پلتفرم (مثل `colorama` فقط win32 و `uvloop` غیر win32)؛ pip-tools فقط برای پلتفرم جاری resolve می‌کند.
  - `scripts/lock.py` تنها منبع flagهاست و هر دو lock (`requirements.lock`، `requirements-dev.lock`) را می‌سازد. pinهای موجود حفظ می‌شوند مگر pyproject تغییر کند، پس اجرای دوباره diff ندارد (بررسی شد). `--upgrade` برای ارتقای همه.
  - CI: نصب با `--require-hashes --no-deps -r requirements-dev.lock`، بعد `--no-deps -e .`؛ step «Lock drift check» lockها را دوباره می‌سازد و با `git diff --exit-code` در صورت تفاوت fail می‌شود. کلید cache pip روی `requirements-dev.lock`.
  - Dockerfile: lock runtime قبل از کد کپی و با `--require-hashes --no-deps` نصب می‌شود (layer تا تغییر lock cache می‌ماند)، بعد `pip install --no-deps .`. `pip install --upgrade pip` حذف شد چون نصب بدون hash بود.
  - ریسک باقی‌مانده (پذیرفته): `pip install --no-deps .` در build isolation پکیج `hatchling` را بدون hash می‌گیرد (فقط backend ساخت، داخل image نصب نمی‌شود).
  - lock نسخه‌های جدیدتر از venv محلی را pin کرد (مثلاً SQLAlchemy 2.1.4، FastAPI 0.143.0). اعتبارسنجی در venv تازه که فقط از lock نصب شد: pytest 623 passed، ruff، format و mypy سبز؛ `docker compose build api` موفق و `pip check` داخل image سالم.
  - **اقدام کاربر (اختیاری):** venv محلی را با دستور نصب جدید CLAUDE.md بخش ۵ با lock هم‌نسخه کنید.
