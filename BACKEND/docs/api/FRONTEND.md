# یادداشت‌های frontend — Project AK API (HANDOFF-01)

قرارداد دقیق endpointها در [openapi.json](openapi.json) است. این فایل با `python scripts/export_openapi.py` ساخته می‌شود و یک تست در CI بررسی می‌کند که با کد هم‌خوان باشد. این یادداشت رفتارهایی را توضیح می‌دهد که از schema دیده نمی‌شوند. مرجع نیازمندی‌ها `sources/Project-AK-PRD.md` است و تصمیم‌ها در `docs/project/DECISIONS.md` (ADR-NNN) ثبت شده‌اند.

## ۱. قرارداد کلی
- base URL: `/api/v1`. همه بدنه‌ها و پاسخ‌ها JSON هستند و نام فیلدها snake_case است. نام‌های camelCase در PRD فقط نمادین‌اند.
- پول همیشه عدد صحیح **تومان** است (`currency: "TOMAN"`). هر قیمت، تخفیف، مالیات، هزینه ارسال یا موجودی که کلاینت بفرستد نادیده گرفته می‌شود یا 400 می‌گیرد. هرگز مبلغی را در frontend محاسبه و ارسال نکن؛ فقط نمایش بده.
- زمان‌ها ISO 8601 با timezone هستند (UTC).
- شکل خطا ثابت است:
  ```json
  {"error": {"code": "PRICE_CHANGED", "message": "...", "details": [{"type": "price_changed", "quote": {}}]}, "request_id": "..."}
  ```
  برای منطق UI فقط به `error.code` و `details[].type` تکیه کن. `message` برای توسعه‌دهنده است و ترجمه نمی‌شود. `request_id` در header `X-Request-ID` هم می‌آید؛ آن را در گزارش خطا نشان بده.
- status: 400 ورودی نامعتبر (`VALIDATION_ERROR`، `details[].field`)، 401 احراز هویت، 403 مجوز یا حساب غیرفعال، 404 ناموجود یا متعلق به دیگری (هرگز 403 برای منبع دیگران)، 409 تعارض وضعیت، 422 قانون کسب‌وکار، 429 با header `Retry-After` (ثانیه)، 503 سرویس در دسترس نیست.
- query parameter ناشناخته → 400. فیلد ناشناخته در بدنه → 400 (به‌جز فیلدهای سیستمی که بی‌صدا حذف می‌شوند).
- پاسخ‌های حساس (token، سبد، سفارش، پرداخت، قیمت و موجودی) `Cache-Control: no-store` دارند. آن‌ها را cache نکن.

## ۲. cookieها و CORS
| cookie | ویژگی‌ها | کاربرد |
|---|---|---|
| `refresh_token` | `HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth`، ۳۰ روز لغزنده | فقط `/auth/refresh` و `/auth/logout` آن را می‌خوانند |
| `cart_token` | `HttpOnly; Secure; SameSite=Lax; Path=/api/v1`، ۳۰ روز لغزنده | سبد مهمان؛ بعد از ورود پاک می‌شود |

- هر دو `HttpOnly` هستند و JS نمی‌تواند آن‌ها را بخواند یا بنویسد. هرگز token را در body یا query نفرست.
- همه درخواست‌ها را با `credentials: "include"` (fetch) یا `withCredentials: true` (axios) بفرست. وگرنه cookieها فرستاده نمی‌شوند و Set-Cookie هم اعمال نمی‌شود.
- origin frontend باید در `CORS_ORIGINS` بک‌اند باشد (`*` با credentials کار نمی‌کند). در production این مقدار الزامی است و `*` ممنوع است؛ بدون آن API بالا نمی‌آید. headerهای مجاز: `Authorization`، `Content-Type`، `X-Request-ID`، `Idempotency-Key`. headerهای قابل‌خواندن: `X-Request-ID` و `Retry-After`.
- `SameSite=Strict` یعنی frontend و API باید **same-site** باشند (یک دامنه ثبت‌شده، مثل `shop.example.com` و `api.example.com`). روی دو دامنه متفاوت، refresh cookie فرستاده نمی‌شود و کاربر بعد از ۱۵ دقیقه خارج می‌شود. در dev، `localhost:5173` و `localhost:8000` same-site هستند.
- `Secure`: فقط روی https، یا روی `http://localhost` در Chrome و Firefox. Safari روی http localhost cookie Secure را ذخیره نمی‌کند؛ برای تست Safari از https محلی استفاده کن.
- همیشه `Content-Type: application/json` بفرست. endpointهای دارای بدنه JSON نوع دیگر (مثل فرم) را با 400 رد می‌کنند. POSTهای بدون بدنه (refresh، logout، `acknowledge-prices`) در برابر CSRF به SameSite cookie و Bearer تکیه دارند.

## ۳. ورود و access token
1. `POST /auth/request-otp {mobile}` → `expires_in_seconds` و `resend_after_seconds`. دکمه ارسال دوباره را تا `resend_after_seconds` غیرفعال کن. 429 `OTP_RATE_LIMITED` → از `Retry-After` استفاده کن.
2. `POST /auth/verify-otp {mobile, code}` → `{access_token, token_type: "bearer", expires_in_seconds}` به‌همراه Set-Cookie `refresh_token`. کد اشتباه، منقضی یا مصرف‌شده همه یک پاسخ دارند: 401 `OTP_INVALID`. حساب غیرفعال یا مسدود → 403 `FORBIDDEN`. در همین درخواست، سبد مهمان در سبد کاربر ادغام و `cart_token` پاک می‌شود. اگر ادغام شکست بخورد، ورود همچنان موفق است و cookie برای ورود بعدی می‌ماند. بعد از ورود `GET /cart` را دوباره بخوان.
3. access token را **فقط در حافظه** نگه دار (نه localStorage) و با `Authorization: Bearer <token>` بفرست. عمر آن ۹۰۰ ثانیه است.
4. `GET /auth/me` نقش‌ها و مجوزهای کاربر را برمی‌گرداند. UI پنل را با مجوزها کنترل کن، نه با نام نقش. تصمیم نهایی همیشه با سرور است.
5. `POST /auth/logout` (با cookie) نشست را باطل می‌کند. access فعلی هم فوراً باطل می‌شود.

### refresh: باید single-flight باشد (حیاتی)
- `POST /auth/refresh` (بدون بدنه، فقط cookie) refresh token را **می‌چرخاند**: token قبلی باطل می‌شود و token جدید در cookie می‌آید. access قبلی هم فوراً باطل می‌شود (ADR-017، ADR-018).
- ارائه refresh باطل‌شده **کل خانواده نشست را باطل می‌کند** (reuse detection) و کاربر در همه تب‌ها خارج می‌شود. grace period وجود ندارد: **دو refresh همزمان با یک cookie هم reuse حساب می‌شوند.**
- قاعده:
  - در هر لحظه فقط یک refresh در کل مرورگر، بین همه تب‌ها و درخواست‌ها، در جریان باشد.
  - داخل یک تب: یک promise مشترک. هر 401 منتظر همان refresh می‌ماند و بعد یک‌بار retry می‌کند.
  - بین تب‌ها: Web Locks API (`navigator.locks.request("ak-auth-refresh", ...)`)، یا BroadcastChannel با رهبر واحد. access جدید را با BroadcastChannel به تب‌های دیگر بده، چون access قبلی آن‌ها هم باطل شده است.
  - داخل lock، قبل از refresh بررسی کن که تب دیگری همین الان access تازه نگرفته باشد.
- refresh پیشگیرانه: حدود ۶۰ ثانیه قبل از `expires_in_seconds` (داخل همان lock).
- 401 از refresh یعنی نشست تمام شده است. state را پاک کن، به صفحه ورود ببر و retry نکن. هرگز refresh را در حلقه retry نکن.

## ۴. سبد و flagهای تغییر قیمت
- مهمان و کاربر هر دو از `/cart` استفاده می‌کنند. مهمان با cookie و کاربر با Bearer شناخته می‌شود. header `Authorization` نامعتبر همیشه 401 است و هرگز به مهمان برنمی‌گردد. پس token منقضی را اول refresh کن، یا header را نفرست.
- `GET /cart` همیشه با محاسبه سرور برمی‌گردد. بدون سبد، سبد خالی برمی‌گردد و سبدی ساخته نمی‌شود. `shipping_amount` در سبد همیشه 0 است (انتخاب در checkout).
- flagهای هر خط (ADR-041):
  - `available: false`: خط دیگر قابل خرید نیست و مبالغش null است. عنوان را نشان بده و حذف خط را پیشنهاد کن.
  - `stock_status`: `ok`، `insufficient` یا `out_of_stock`. عدد موجودی هرگز در پاسخ نیست. فقط بگو «موجودی کافی نیست» و کاهش تعداد را پیشنهاد کن.
  - `price_changed: true` به‌همراه `previous_unit_price`: قیمت نهایی واحد با قیمتی که مشتری آخرین بار دیده فرق دارد. قیمت قبلی را خط‌خورده نشان بده.
  - `discount`: `{code, applied, reason}`. `applied: false` با `reason` (`invalid`، `expired`، `exhausted`، `user_exhausted`، `below_minimum`، `no_eligible_lines`) یعنی کد الان اعمال نمی‌شود. `applied: true` تضمین نیست؛ شمارش قطعی هنگام ثبت سفارش است.
  - `has_changes`: هر یک از موارد بالا. یک banner «سبد شما تغییر کرده است» نشان بده.
- `POST /cart/acknowledge-prices` (بدون بدنه): مشتری قیمت‌های جدید را دید و پذیرفت. flagهای `price_changed` پاک می‌شوند و همان شکل `GET /cart` برمی‌گردد. هر نوشتن روی یک خط هم مبنای همان خط را به‌روز می‌کند.
- این flagها فقط UX هستند. امنیت مبلغ با fingerprint است (بخش ۵).
- خطاهای افزودن: 409 `INSUFFICIENT_STOCK`؛ 404 تنوع عمومی نیست؛ 422 `is_purchasable = false` یا سقف ۵۰ خط. `PATCH /cart/items/{id}` فقط `quantity` می‌گیرد. برای تغییر تنوع، خط را حذف و تنوع جدید را اضافه کن.
- `POST /cart/discount {code}`: هر تلاش ناموفق شمرده می‌شود. بعد از سقف → 429 `RATE_LIMITED` با `Retry-After`. کد با شکل نامعتبر هم 422 `DISCOUNT_NOT_APPLICABLE` است، نه 400. `DELETE /cart/discount` idempotent است.

## ۵. checkout و ثبت سفارش
1. `POST /checkout/validate {address_id, shipping_method_id}` (ورود لازم است) → quote کامل با `fingerprint`. همین quote را به مشتری نشان بده.
2. `POST /orders {address_id, shipping_method_id, fingerprint}` با header `Idempotency-Key` → 201 با سفارش، `order_number` و `reservation_expires_at`. موجودی ۱۵ دقیقه رزرو شده است. شمارش معکوس را نشان بده. سبد خالی نمی‌شود؛ بعد از پرداخت موفق فقط تعداد سفارش‌داده‌شده از آن کم می‌شود.
- 409 `PRICE_CHANGED`: quote جدید در `details[0].quote` است. آن را نشان بده، تأیید دوباره بگیر و با fingerprint جدید و **کلید جدید** دوباره بفرست.
- 409 `ORDER_PENDING`: کاربر یک سفارش پرداخت‌نشده با رزرو زنده دارد (`details[0].order_number`). به پرداخت همان سفارش ببر یا لغوش را پیشنهاد کن.
- 409 `INSUFFICIENT_STOCK`، 422 `cart_empty`، `line_unavailable`، `shipping_method_unavailable`، `DISCOUNT_NOT_APPLICABLE`: کاربر را به سبد یا checkout برگردان.
- 401 `MOBILE_NOT_VERIFIED`: ورود با OTP لازم است.
- لغو: `POST /orders/{id}/cancel` فقط برای سفارش `pending_payment`. وقتی payment در جریان است (مشتری در درگاه است) → 409 `PAYMENT_IN_PROGRESS`. لغو تکراری 200 با وضعیت فعلی برمی‌گرداند.
- `GET /orders` (صفحه‌بندی، `status`، `sort=newest|oldest`) و `GET /orders/{order_number}` سفارش‌های خود کاربر را برمی‌گردانند (ACC-01). جزئیات `payments`، `history`، `payment_deadline`، `can_pay` و `can_cancel` دارد. دکمه‌های پرداخت و لغو را با `can_pay` و `can_cancel` نمایش بده. سفارش مهلت‌گذشته تا وقتی job آن را لغو کند `pending_payment` می‌ماند، ولی هر دو flag آن false است.

## ۶. Idempotency-Key
- لازم برای `POST /orders` و `POST /payments/init`. نبود یا نامعتبر بودن آن → 400. مقدار: ۱ تا ۲۵۵ کاراکتر ASCII قابل چاپ بدون فاصله. `crypto.randomUUID()` کافی است.
- یک کلید برای هر **قصد کاربر** بساز (هر کلیک «ثبت سفارش» یا «پرداخت» با همان بدنه)، نه برای هر درخواست HTTP. در retry بعد از خطای شبکه یا timeout، **همان کلید و همان بدنه** را بفرست. سرور پاسخ اولیه را برمی‌گرداند و سفارش یا پرداخت دوم ساخته نمی‌شود.
- اگر بدنه عوض شد (fingerprint، آدرس یا روش ارسال)، کلید جدید بساز. همان کلید با بدنه متفاوت → 422 `IDEMPOTENCY_KEY_REUSED`.
- فقط پاسخ موفق (2xx) ذخیره می‌شود. بعد از هر 4xx یا 5xx همان کلید دوباره قابل استفاده است. محدوده هر کلید یک کاربر و یک endpoint است و مهلت آن ۲۴ ساعت.
- replay همیشه همان پاسخ اولیه است، حتی اگر سفارش بعداً لغو شده باشد. برای وضعیت فعلی به آن تکیه نکن.
- `POST /payments/init` با همان کلید وقتی درخواست اول هنوز با درگاه در حال صحبت است → 409 `PAYMENT_IN_PROGRESS`. چند ثانیه بعد با همان کلید retry کن.

## ۷. پرداخت
1. `POST /payments/init {order_id}` (با `Idempotency-Key`) → 201 `{payment_id, order_id, order_number, amount, currency, redirect_url, gateway_expires_at, reservation_expires_at}`. مرورگر را به `redirect_url` ببر. مبلغ را فقط نمایش بده.
2. درگاه مرورگر را به صفحه نتیجه frontend برمی‌گرداند (`PAYMENT_CALLBACK_URL` بک‌اند به این صفحه اشاره می‌کند). صفحه نتیجه reference را برمی‌دارد، `POST /payments/callback {"reference": "..."}` را صدا می‌زند و صفحه را از پاسخ می‌سازد. این endpoint عمومی است و token نمی‌خواهد. پارامترهای درگاه هیچ اثری ندارند، چون سرور خودش با درگاه verify می‌کند.
3. پاسخ callback پردازش‌شده همیشه 200 است: `{outcome, order_number, order_status, order_payment_status, payment_status}`.

| `outcome` | معنا | UI |
|---|---|---|
| `paid` | پرداخت تأیید شد و سفارش `confirmed` است | صفحه موفقیت با شماره سفارش |
| `already_processed` | قبلاً اعمال شده (refresh صفحه) | بر اساس `order_status` و `payment_status` نمایش بده |
| `pending` | درگاه هنوز نتیجه قطعی نداده است | «در حال بررسی»؛ چند ثانیه بعد همان callback را دوباره بفرست (با backoff؛ سرور هم خودش تطبیق می‌دهد) |
| `failed` | پرداخت ناموفق؛ رزرو و کد تخفیف تا پایان مهلت نگه داشته می‌شوند | دکمه «تلاش دوباره» → init جدید با کلید جدید |
| `amount_mismatch` | مبلغ درگاه با سفارش نمی‌خواند؛ نیاز به بازپرداخت دستی | «پرداخت ناموفق؛ مبلغ برگشت داده می‌شود». تلاش دوباره ممکن است |
| `refund_required` | پول دریافت شد ولی رزرو منقضی شده بود و سفارش لغو شد | «سفارش لغو شد؛ مبلغ برگشت داده می‌شود» با شماره سفارش |
| `duplicate_payment` | پرداخت دوم روی سفارشی که قبلاً پرداخت شده بود | «سفارش قبلاً پرداخت شده؛ پرداخت دوم برگشت داده می‌شود» |

- callback: 404 reference ناشناخته، 429 بیش از حد (`Retry-After`)، 400 بدنه نامعتبر. 503 `PAYMENT_GATEWAY_UNAVAILABLE` یعنی verify با درگاه شکست خورد و چیزی تغییر نکرد. این حالت بعد از یک پرداخت واقعی هم ممکن است، پس صفحه خطا نشان نده: «در حال بررسی» را نشان بده و همان callback را با backoff دوباره بفرست. job تطبیق سرور هم آن را می‌بندد.
- init دوباره، مثلاً وقتی مشتری صفحه درگاه را بست:
  - session درگاه هنوز معتبر است: همان `redirect_url` برمی‌گردد.
  - session منقضی شده و درگاه نتیجه قطعی نداده است: 409 `PAYMENT_IN_PROGRESS` (`details[0].type = session_open`). «پرداخت قبلی در حال بررسی است» را نشان بده و کمی بعد دوباره امتحان کن.
  - پرداخت قبلی پرداخت شده بود: init بعدی 422 `INVALID_STATE_TRANSITION` (`order_not_payable`) می‌گیرد.
- خطاهای init:
  - 409 `RESERVATION_EXPIRED`: مهلت سفارش تمام شده یا کمتر از ۶۰ ثانیه مانده است (`details[0].type = reservation_expired | too_late`). سفارش باید از سبد دوباره ثبت شود.
  - 422 `INVALID_STATE_TRANSITION`: سفارش قابل پرداخت نیست (`order_not_payable`، `zero_amount`).
  - 503 `PAYMENT_GATEWAY_UNAVAILABLE`: درگاه در دسترس نیست؛ «چند لحظه بعد تلاش کنید».
  - 404: سفارش دیگران یا ناموجود.
- درگاه fake (فقط development و staging): `redirect_url` به `GET /api/v1/payments/fake/{reference}` اشاره می‌کند که JSON است، نه صفحه. در dev یک صفحه ساده بساز که `POST /api/v1/payments/fake/{reference}/complete {"result": "paid" | "failed"}` را صدا بزند (`amount_rial` اختیاری برای شبیه‌سازی مبلغ اشتباه)، سپس به صفحه نتیجه با همان reference برود.

## ۸. سایر نکات
- هیچ endpointی عدد موجودی عمومی برنمی‌گرداند. فقط `availability` (`in_stock`، `low_stock`، `out_of_stock`) و `purchasable` برمی‌گردد.
- آدرس و سفارش دیگران همیشه 404 است. پیام «پیدا نشد» نشان بده.
- rate limitها بر اساس IP هستند. پشت proxy به پیکربندی trusted-proxy (OPS-04) نیاز دارند.
- endpointهای `/admin/*` با مجوز (permission) کنترل می‌شوند. 403 یعنی مجوز نداری، نه اینکه وارد نشده‌ای.
