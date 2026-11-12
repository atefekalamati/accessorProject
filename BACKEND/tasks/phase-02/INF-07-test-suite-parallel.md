# INF-07 — Test-suite performance (pytest-xdist, one database per worker)

**Status:** COMPLETE · **Priority:** MEDIUM · **Estimate:** 1.5h (estimate) · **Deadline:** — · **Dependencies:** FND-06, FND-07, SEC-06 · **Level:** LOW

## Objective
کل suite زیر ۴ دقیقه، محلی و در CI. درخواست کاربر در 2026-10-12 (batch جدا، قبل از INV-05). pytest-xdist (dev، از طریق lock) با تأیید کاربر.

## PRD reference
— (زیرساخت تست).

## Acceptance Criteria
- [x] `pytest --durations` بررسی شد: هیچ sleep واقعی یا انتظار همزمانی در تست‌ها نیست (همزمانی فقط با `asyncio.gather`). هزینه، round-trip دیتابیس در حدود ۱۳۰۰ تست است، نه چند تست کند.
- [x] `pytest-xdist` در `[project.optional-dependencies].dev` و `requirements-dev.lock` (با hash). `addopts` شامل `-n auto` است (`-n 0` برای اجرای تک‌پروسه).
- [x] هر worker دیتابیس خودش را دارد: `<base>_test` → `<base>_<gwN>_test`. نام با `unsafe_test_database_reason` دوباره چک می‌شود. دیتابیس از `template0` ساخته می‌شود (اگر نباشد) و `synchronous_commit = off` می‌گیرد. guard اصلی (`pytest_sessionstart`، exit 3) بدون تغییر است.
- [x] شناسه تست‌ها در همه workerها یکسان است: UUID تصادفی در parametrize (`test_admin_products._ID`) ثابت شد.
- [x] تست واحد برای نام دیتابیس worker (`test_worker_database_keeps_the_test_suffix`).
- [x] محلی: 5:25 → 2:38 (1339 passed). CI (repo خصوصی، runner با ۲ vCPU): سریال 107–166s در ۶ run قبلی، موازی 141s؛ تفاوت در حد نویز است. CI موازی می‌ماند تا مشکلات خاص xdist را بگیرد.
- [x] ruff، format و mypy سبز.

## Implementation Notes
- `tests/conftest.py`: `worker_database_url`، `_prepare_worker_database` و fixture `database_url(worker_id)`. بقیه fixtureها بدون تغییر.
- ۸ worker و ۴ worker تقریباً هم‌زمان تمام شدند (2:38 در برابر 2:51)؛ گلوگاه محلی CPU ماشین و VM داکر است.
- دیتابیس‌های worker در همان container `postgres-test` هستند و با `rm -f` آن پاک می‌شوند.

## Validation
```powershell
python -m pytest -q   # با TEST_DATABASE_URL؛ موازی
python -m pytest -q -n 0 tests/test_x.py   # تک‌پروسه برای debug
```

## Log
- 2026-10-12: CI با `-n 0` (`f95ec76`) 151s شد، پس مقایسه قبلی نویز بود. ۶ run سریال قبلی 107–166s. CI به موازی برگشت.
- 2026-10-12: CI اول (`0ef7d43`) سبز، 1340 passed در 141s با ۲ worker در برابر 121s سریال؛ CI به `-n 0` برگشت. کاهش هزینه هر تست (engine و app برای هر تست) refactor بزرگ‌تری است و پیشنهاد جدا می‌شود.
- 2026-10-12: پیاده‌سازی. baseline سریال 324s (call 222s، setup 68s، teardown 41s). با xdist: 167s، با `synchronous_commit=off`: 156s. ruff و mypy سبز.
