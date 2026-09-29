# FND-01 — App skeleton, settings, /health, API docs

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 4h (estimate) · **Deadline:** — · **Dependencies:** —

## Objective
FastAPI app factory، تنظیمات از env با اعتبارسنجی، CORS امن، endpointهای health و مستندات API.

## PRD reference
«معماری سیستم»

## Acceptance Criteria
- [x] `create_app()` در `app/main.py` با lifespan (engine و session factory).
- [x] `Settings` درایور `postgresql+asyncpg` و `JWT_SECRET` حداقل ۳۲ کاراکتر را الزامی می‌کند. در production، CORS wildcard و mock OTP رد می‌شوند.
- [x] `GET /health` و `GET /api/v1/health` پاسخ 200 با `status`، `version`، `environment` و `request_id` می‌دهند.
- [x] `/docs`، `/redoc` و `/openapi.json` پاسخ 200 می‌دهند.

## Implementation Notes
`app/main.py`، `app/core/config.py`، `app/shared/health/`، `tests/test_health.py`، `tests/test_settings.py`.

## Validation
```powershell
python -m pytest tests/test_health.py tests/test_settings.py
```

## Log
- 2026-09-13: پیاده‌سازی شد (commit `48f1542`، مرحله ۰ نقشه راه قدیمی).
- 2026-09-29: تأیید شد. مجموعه تست سبز است و smoke test با `uvicorn` روی `/health` پاسخ 200 داد.
