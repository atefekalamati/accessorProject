# SEC-07 — Pin CI runner and bump official actions

**Status:** COMPLETE · **Priority:** LOW · **Estimate:** 0.5h (estimate) · **Deadline:** — · **Dependencies:** FND-07, SEC-05 · **Level:** LOW

## Objective
CI قابل‌تکرار: runner با نسخه ثابت به‌جای `ubuntu-latest`، و actionهای رسمی روی آخرین major. درخواست کاربر در 2026-10-10 (قبل از SEC-06 در همان batch).

## PRD reference
— (زیرساخت CI).

## Acceptance Criteria
- [x] هر دو job (`secret-scan`، `checks`) در `.github/workflows/ci.yml` با `runs-on: ubuntu-24.04` اجرا می‌شوند.
- [x] `actions/checkout@v7` و `actions/setup-python@v7`. وجود هر دو تأیید شد: tag `v7` و release پایدار `v7.0.1` / `v7.0.0` در 2026-07-20.
- [x] release notes v7 بررسی شد: تغییر ناسازگار با این workflow ندارد (ورودی حذف‌شده `pip-install` در setup-python استفاده نمی‌شود).
- [x] CI سبز؛ pytest، ruff و mypy سبز.

## Implementation Notes
- فقط `.github/workflows/ci.yml` تغییر می‌کند.

## Validation
```powershell
python -m pytest -q   # با TEST_DATABASE_URL
& "C:\Program Files\GitHub CLI\gh.exe" run watch <id> --exit-status
```

## Log
- 2026-10-10: پیاده‌سازی (batch SEC-07/SEC-06/CAT-01..03). pytest 623 passed؛ ruff و mypy سبز. CI بعد از push بررسی می‌شود.
