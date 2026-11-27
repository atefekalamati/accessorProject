# PAY-07 — Real payment gateway adapter: Zarinpal v4

**Status:** IN_PROGRESS (کد در PR #13؛ منتظر merge کاربر و E2E دستی sandbox) · **Priority:** HIGH · **Estimate:** 5h (estimate) · **Deadline:** — · **Dependencies:** PAY-01, DEC-08 (D8) · **Level:** HIGH

## Objective
`ZarinpalGateway` پشت همان interface درگاه (OPS-10)؛ تبدیل تومان↔ریال فقط داخل adapter؛ قراردادهای `init` و `callback` ثابت.

## PRD reference
«پرداخت» ✓؛ ADR-001، ADR-009، ADR-048، ADR-049، ADR-051، ADR-052، ADR-061، [ADR-064](../../docs/project/DECISIONS.md).

## Plan
plan تأییدشده کاربر (2026-11-27) با پاسخ چهار سؤال: httpx runtime با نسخه lock؛ coverage یک‌باره با `uv run --with coverage`؛ -50 → failed `gateway_amount_rejected`؛ guard production تا go-live. جزئیات طراحی در ADR-064.

## Acceptance Criteria
- [x] adapter با endpointها، فیلدها و کدهای v4 (100، 101، -50، -51، -54/-55، کدهای merchant) طبق docs رسمی؛ `currency: "IRR"` و ریال فقط داخل adapter.
- [x] verify همیشه سمت سرور با مبلغ ذخیره‌شده؛ `Status` هرگز مبنا نیست؛ -51 با inquiry.
- [x] -50 → failed `gateway_amount_rejected` با log ERROR و audit؛ بدون `refund_required`.
- [x] بدون retry روی request؛ retry محدود (۳) روی verify و inquiry با یک deadline مشترک داخل timeout.
- [x] log و ذخیره بدون merchant id و `card_hash`؛ فقط PAN ماسک‌شده.
- [x] env: `PAYMENT_PROVIDER` (به‌همراه `PAYMENT_GATEWAY` قدیمی)، `ZARINPAL_MERCHANT_ID`، `ZARINPAL_SANDBOX`؛ placeholder در `.env.example`.
- [x] production fail-closed برای هر درگاه تا go-live (تست شده).
- [x] تست‌ها فقط با HTTP mock (`httpx.MockTransport`؛ بدون dependency جدید): success، NOK/cancel، شکست verify، amount mismatch، 101/تکراری، callback همزمان، موفقیت دیرهنگام بعد از انقضای رزرو، IDOR، مبلغ دست‌کاری‌شده؛ به‌علاوه reconciliation و نبود secret.
- [x] coverage ماژول payments ≥ ٪۹۰: کل ٪۹۵، `zarinpal.py` ٪۹۹ (یک‌باره با `uv run --no-project --with coverage`، `--concurrency=greenlet,thread`).
- [x] `_code` هر دو شکل `errors` (object و آرایه) را می‌خواند؛ تست برای هر کدام.
- [x] init بالای `PAYMENT_MAX_AMOUNT` (پیش‌فرض ۱۰۰٬۰۰۰٬۰۰۰ تومان) → 422 `PAYMENT_AMOUNT_TOO_LARGE` قبل از درگاه؛ تست مرزی.
- [x] docs: go-live checklist در README (با auto_verify و سقف مبلغ)، FRONTEND.md §۷، OpenAPI (توضیح 422 روی init).
- [x] بازبین opus روی plan و diff (دو دور)؛ CI سبز (checks، staging-smoke، secret-scan)؛ PR #13 به master (بدون merge).
- [ ] E2E دستی sandbox (کاربر، یک‌بار؛ قبل از go-live)؛ شکل واقعی `errors` و عمر authority ثبت شود.

## Implementation Notes
- `app/modules/payments/gateways/zarinpal.py`؛ ساخت و بستن در `gateways/__init__.py` (`build_payment_gateway`، `close_payment_gateway`)، lifespan و `jobs._main`.
- mock stateful API در `tests/zarinpal_mock.py`؛ unit در `tests/test_payment_zarinpal.py`؛ جریان کامل در `tests/test_payments_zarinpal.py`؛ Zarinpal در `tests/test_provider_contracts.py`.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-11-27: docs رسمی v4 خوانده شد (request، verify، inquiry، unVerified، errorList، sandbox، currency، session-validation). نکات مستند‌نشده: واحد پیش‌فرض، عمر authority و شکل کامل بدنه خطا؛ طراحی آن‌ها را دور می‌زند (ADR-064).
- 2026-11-27: بازبین opus روی plan: ۲ BLOCKER رفع شد. -50 دیگر به refund نمی‌رود (تصمیم کاربر). خطاهای مخصوص یک payment، PENDING هستند تا دور reconciliation متوقف نشود. ۶ SHOULD هم اعمال شد: alias با kwarg، guard production، جایگزینی ADR-051 #5، ریسک موفقیت دیرهنگام، تست‌های اضافه و بستن client.
- 2026-11-27: بازبین opus روی diff: BLOCKER نداشت؛ ۵ SHOULD:
  - deadline مشترک verify و inquiry در ٪۹۰ timeout: رفع شد. تست inquiry کند داخل `call_gateway` اضافه شد.
  - پاسخ بدون کد → `GatewayUnavailable`: رفع شد.
  - تقدم kwarg بر env: بررسی شد. pydantic-settings kwarg را بر env مقدم می‌کند؛ تست شد. `export_openapi` حالا `payment_provider` می‌دهد.
  - بعد از بستن، `app.state.payment_gateway = None` و client بسته‌شده → unavailable: رفع شد.
  - فایل task و PROGRESS: رفع شد.
  - NITها هم اعمال شدند: comment، timeout کل هر call با `asyncio.timeout`، حذف `__context__`، `errors.code` رشته‌ای، assert log retry، بستن clientهای تست، `PAYMENT_PROVIDER` در CI.
- 2026-11-27: cross-check کامل با docs و sampleها (request، verify، inquiry، errorList، sandbox، currency): ۵ تفاوت. به تصمیم کاربر:
  - (۱) `_code` شکل آرایه‌ای `errors` را هم می‌خواند.
  - (۲) سقف مبلغ در init با 422 `PAYMENT_AMOUNT_TOO_LARGE` و setting `PAYMENT_MAX_AMOUNT`.
  - (۳) تا (۵) بدون تغییر پذیرفته شدند؛ `auto_verify` به go-live checklist اضافه شد.
- 2026-11-27: بازبین opus روی diff دوم: BLOCKER نداشت؛ ۴ SHOULD رفع شد:
  - کد از `errors` فقط منفی و فقط با رقم ASCII؛ 100 یا 101 فقط از `data.code` عددی، پس بدنه خطا هرگز PAID نمی‌شود. تست شد.
  - تست شکل خطا حالا کد دقیق را assert می‌کند.
  - تست سقف مبلغ با همان Idempotency-Key و رزرو active.
  - `zero_amount` در OpenAPI و FRONTEND زیر `BUSINESS_RULE_VIOLATION` است.
  - NITها: `BusinessRuleError` برای سقف مبلغ؛ ترتیب بررسی‌ها و حداقل مبلغ در ADR و checklist؛ `RuntimeError` فقط وقتی client بسته است.
- 2026-11-27: suite کامل روی دیتابیس تست تازه: 2567 passed (۱ warning قدیمی در ACC-06). ruff، format و mypy سبز.
  - اجرای قبلی روی container تست ۲۴ ساعته 263 خطای setup داشت (`uq_users_phone`). علت: downgrade migration `0036` روی دیتابیسی که placeholderهای downgrade قبلی را دارد دوباره قابل اجرا نیست. باگ قدیمی و جدا از PAY-07 است؛ CI همیشه دیتابیس تازه دارد. به کاربر گزارش شد.
- 2026-11-27: commit `66d63ff`، PR #13. CI run `46048288786` (pull_request) و `46048246811` (push) سبز: checks، staging-smoke و secret-scan pass؛ publish-image skipped (فقط روی master).
