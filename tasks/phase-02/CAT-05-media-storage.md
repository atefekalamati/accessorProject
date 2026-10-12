# CAT-05 — Media model + storage interface + upload

**Status:** COMPLETE · **Priority:** MEDIUM · **Estimate:** 4h (estimate) · **Deadline:** — · **Dependencies:** CAT-02, ADR-009 · **Level:** HIGH

## Objective
پایه رسانه: storage پشت interface (local و in-memory)، پردازش امن تصویر (تشخیص magic bytes، سقف حجم و ابعاد، re-encode بدون metadata)، جدول‌های `media` و `product_media`، endpoint `POST /admin/media`، و جایگزینی `categories.image_url` با `image_media_id`. آپلود و مدیریت تصویر محصول در CAT-11 انجام می‌شود.

## PRD reference
«محصولات» ✓ (قواعد رسانه، ProductMedia)؛ «دسته‌بندی محصولات» ✓ (بنر دسته)؛ ADR-009، ADR-020، ADR-024، ADR-025، ADR-028.

## Acceptance Criteria
- [x] `python-multipart` 0.0.32 و `pillow` 12.3 از طریق lock با hash اضافه شدند (تصمیم کاربر: گزینه الف).
- [x] سقف حجم هنگام stream: Content-Length بزرگ و stream بدون Content-Length هر دو قبل از خواندن کامل body رد می‌شوند (400). فقط یک فایل در فیلد `file`، فیلد اضافه ممنوع، spool به temp file، و بستن form در هر حالت.
- [x] authz قبل از خواندن body: بدون token → 401 و نقش بی‌مجوز → 403، حتی با body بزرگ‌تر از سقف.
- [x] فقط jpeg، png و webp بر اساس magic bytes (نام و Content-Type فایل نادیده گرفته می‌شوند). ابعاد قبل از decode از header بررسی می‌شوند و decompression bomb، تصویر animated و تصویر truncated → 400.
- [x] re-encode از pixel خام: EXIF، XMP، ICC، COM و text chunk حذف می‌شوند، payload پس از تصویر (polyglot) حذف می‌شود و orientation اعمال می‌شود. حداکثر ۲ decode همزمان.
- [x] storage: کلید را سرور می‌سازد، regex و resolve زیر root بررسی می‌شوند و نوشتن اتمیک است. حذف فایل ناموجود خطا نیست. production با `memory` شروع نمی‌شود.
- [x] settingها: `MEDIA_STORAGE`، `MEDIA_ROOT` و `MEDIA_PUBLIC_BASE_URL`. host آدرس پایه باید در `MEDIA_ALLOWED_HOSTS` باشد و production فقط https می‌پذیرد (fail-closed). placeholder در `.env.example` و مقدار dev در `.env` محلی.
- [x] جدول `media` (CHECKهای نوع، حجم و ابعاد؛ `storage_key` unique) و `product_media` (`media_id` unique، تصویر اصلی partial unique، composite FK برای تنوع همان محصول). migration `20261010_0012`.
- [x] `POST /admin/media` → 201 با `no-store` و audit `media.uploaded`. اگر نوشتن DB شکست بخورد، فایل ذخیره‌شده حذف می‌شود.
- [x] دسته: `image_media_id` (فیلد محتوایی برای `categories:edit_content`). media ناموجود → 422. پاسخ‌های admin و عمومی `image_url` ساخته‌شده توسط سرور را دارند و media key با یک کوئری خوانده می‌شود.
- [x] pytest، ruff، format و mypy سبز.

## Implementation Notes
- کد: `app/shared/{media,uploads,storage}.py`، `app/db/models/media.py`، `app/modules/media/`، تغییرات `app/modules/catalog/*`، `app/core/config.py` و `app/main.py`.
- تست‌ها: `tests/test_media_processing.py` (unit)، `tests/test_media_api.py`، و به‌روزرسانی تست‌های دسته و settings. فایل `tests/test_catalog_image_url.py` حذف شد.
- **Rollback:** `alembic downgrade -1` جدول‌های media را حذف می‌کند و `image_url` خالی را برمی‌گرداند. بعد از آن `git revert`. lock با همان commit برمی‌گردد.
- **Follow-up:** پاک‌سازی media یتیم (آپلود بدون استفاده، یا crash بین ذخیره فایل و commit) → task OPS. حذف فایل بعد از commit در CAT-11.

## Validation
```powershell
python -m pytest -q   # با TEST_DATABASE_URL
python -m ruff check .; python -m ruff format --check .; python -m mypy app tests
```

## Log
- 2026-10-10: plan متوقف شد چون dependency جدید بود (استثنای AUTOPILOT). کاربر گزینه الف را تأیید کرد، به‌علاوه سقف stream، حداکثر یک فایل، محدودیت فیلد و spool.
- 2026-10-10: بازبینی plan توسط subagent مستقل: APPROVE WITH CHANGES (۲ major). اعمال شد: re-encode از pixel خام چون Pillow `icc_profile` و `comment` را از `info` بازنویسی می‌کرد. مدل media در ADR-028 ثبت شد و PRD به‌روز شد. نگاشت خطاها، CapacityLimiter، حذف جبرانی روی cancel، composite FK و مقدار دقیق بایت‌ها.
- 2026-10-10: بازبینی diff نهایی: APPROVE WITH CHANGES (۱ major). اعمال شد: هر خطای decode یا EXIF → 400 (با تست fuzz)، ذخیره فایل داخل try جبرانی، ClientDisconnect → 400، و رسانه محصول به‌عنوان بنر دسته → 422 تا حذف رسانه در CAT-11 با FK گیر نکند.
- 2026-10-10: COMPLETE. pytest 881 passed (۵۹ تست بیشتر از قبل، پس از حذف تست‌های image_url)؛ ruff، format و mypy سبز.
