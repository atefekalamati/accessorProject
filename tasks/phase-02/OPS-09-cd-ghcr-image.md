# OPS-09 — CD: image to GHCR

**Status:** COMPLETE · **Priority:** MEDIUM · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** OPS-08 · **Level:** MEDIUM

## Objective
بعد از merge در `master` و سبز شدن همه jobها (secret-scan، checks، staging-smoke)، image API ساخته و در GitHub Container Registry با tagهای `<sha>` و `phase-N` push شود. فقط این job مجوز `packages:write` دارد (ADR-037).

## PRD reference
ADR-037.

## Plan (batch OPS-08/OPS-09)
- job `publish-image` در `ci.yml`: `if: github.event_name == 'push' && github.ref == 'refs/heads/master'`، `needs: [secret-scan, checks, staging-smoke]`، `permissions: {contents: read, packages: write}` فقط در همین job (سطح workflow `contents: read` می‌ماند).
- بدون action بیرونی جدید: `docker login ghcr.io` با `GITHUB_TOKEN` از stdin، `docker build` با label `org.opencontainers.image.source`، push.
- نام image: `ghcr.io/<owner/repo lowercase>-api` (اکنون `ghcr.io/atefekalamati/accessorproject-api`). tag `<sha>` همیشه؛ `phase-N` از پیام merge commit (`feat/phase-N-…` یا `Phase N`)؛ پیدا نشد → فقط `<sha>` و warning.
- git tag `phase-N` را دروازه فاز (گام d) دستی روی merge commit می‌زند، نه این job (بدون `contents: write`).
- ریسک‌ها: دسترسی بیش از حد (permission فقط در job)؛ push image از کد قرمز (needs همه jobها)؛ اعتبارسنجی فقط بعد از merge ممکن است → در گام d دروازه فاز ۲ تأیید می‌شود.
- Rollback: حذف job؛ حذف package از GHCR در صورت نیاز (دستی، توسط کاربر).

## Acceptance Criteria
- [x] job فقط روی push به `master` و بعد از سبز شدن هر سه job اجرا می‌شود؛ `packages:write` فقط در این job.
- [x] tagهای `<sha>` و `phase-N` (تست منطق استخراج N با پیام‌های نمونه، محلی).
- [x] YAML معتبر (parse محلی) و CI شاخه سبز (job روی شاخه skip می‌شود).
- [x] تأیید نهایی push در GHCR: گام d دروازه فاز ۲ (ثبت در Log). فقط بعد از merge قابل بررسی است؛ COMPLETE با این پیگیری.

## Implementation Notes
- job `publish-image` در `.github/workflows/ci.yml` (needs هر سه job، `packages: write` فقط اینجا، token از env و login از stdin، label های OCI source و revision). `scripts/phase_tag.py` شماره فاز را از پیام merge commit درمی‌آورد؛ تست `tests/test_phase_tag.py` (۵ حالت).
- روی شاخه فاز job به‌دلیل شرط `if` اجرا نمی‌شود؛ اجرای واقعی در merge به `master` (گام d دروازه).
- **Rollback:** حذف job و اسکریپت؛ `git revert`.

## Validation
```powershell
python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml'))"
```

## Log
- 2026-10-12: فایل task و plan (batch OPS-08/OPS-09، AUTOPILOT).
- 2026-10-12: YAML parse و تست phase_tag سبز؛ pytest کامل، ruff، format و mypy سبز. COMPLETE؛ تأیید push در GHCR در گام d دروازه فاز ۲.
- 2026-10-12: گام d دروازه: run 38309533589 روی `master` (`e750ddf`) سبز؛ `ghcr.io/atefekalamati/accessorproject-api:e750ddf…` و `:phase-2` با digest یکسان `sha256:ae2c9379…d8f4` push شدند.
