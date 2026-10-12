# CAT-00 — Rewrite «جزئیات محصول» and «محصولات» (admin) requirements

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate; was 2h, two templated sections) · **Deadline:** — · **Dependencies:** — · **Level:** HIGH

## Objective
بخش‌های قالبی «جزئیات محصول» (فروشگاه عمومی) و «محصولات» (پنل مدیریت) در PRD را با الزامات دقیق و قابل‌ردیابی جایگزین کن: product detail، variantها، media و admin products. منبع: بخش‌های مرجع ✓ و ADRها. هیچ ویرایشی روی PRD تا تأیید کاربر اعمال نمی‌شود.

## PRD reference
- بازنویسی: «جزئیات محصول» (خط 1778–1982)، «محصولات» (خط 5886–6090)، و یک خط در «معماری سیستم» ✓ (`GET /products/{id}` → `{slug}`).
- منابع: «معماری سیستم» ✓، «دسته‌بندی محصولات» ✓، «قیمت و مالیات» ✓، «موجودی و رزرو» ✓، «صفحه اصلی» ✓؛ ADR-001، 004، 005، 009، 010، 011، 015، 018؛ PLAN (CAT-02…CAT-11، SD rule).
- تصمیم کاربر (2026-10-09): URL عمومی محصول با slug است و endpointهای admin با id.

## Acceptance Criteria
- [x] پیش‌نویس دو بخش با همان ۱۰ زیربخش PRD نوشته شد؛ endpointهای CRUD قالبی منتقل نشدند.
- [x] همه تغییرات PRD به‌صورت یک unified diff در `docs/project/drafts/CAT-00-prd.diff` (`git apply --check` موفق).
- [x] جدول خلاصه (endpoint/rule · منبع · new/changed) با برچسب `SCOPE?` برای موارد بدون منبع PRD/ADR.
- [x] سازگاری با بخش‌های ✓: قیمت فقط در بک‌اند (عدد صحیح تومان)، نبود عدد موجودی در پاسخ عمومی، موجودی فقط در InventoryItem، SD rule.
- [x] تأیید کاربر روی diff و پاسخ سؤال‌های باز (2026-10-09).
- [x] apply diff روی `sources/Project-AK-PRD.md` در یک commit جدا؛ «✓» روی دو بخش (در diff موجود است).
- [x] ردیف «PRD changes» و ADR-020 (D24: public slug / admin id) و تصمیم‌های کم‌اثر در `DECISIONS.md`.
- [x] حذف `docs/project/drafts/CAT-00-prd.diff` بعد از apply (تاریخچه در git می‌ماند).
- [x] pytest، ruff check، ruff format --check و mypy سبز (بدون تغییر کد).

## Draft summary (endpoint/rule · source · new vs changed)
| # | Endpoint / rule | Source | Status |
|---|---|---|---|
| 1 | `GET /products/{slug}` detail | معماری ✓ `GET /products/{id}` + تصمیم کاربر | changed (+ hunk در معماری ✓) |
| 2 | فقط published؛ 404 یکسان برای draft/archived/soft-deleted | دسته‌بندی ✓ امنیت، SD rule، ADR-015، ADR-018 | new |
| 3 | دسته غیرفعال محصول را پنهان نمی‌کند؛ فقط از breadcrumb حذف می‌شود | — | kept (Q1: صفحه نمایش، از لیست دسته حذف) |
| 4 | purchasable = فعال + `is_purchasable` + `base_price>0` + free>0 | معماری ✓ قوانین، موجودی ✓ مدل | new |
| 5 | sale_price فقط داخل بازه؛ final_price در بک‌اند | قیمت ✓ (saleStartAt/EndAt)، ADR-001 | new |
| 6 | discount_amount/percent (percent floor، فقط نمایشی) | قیمت ✓ «نمایش درصد یا مبلغ تخفیف» | kept (read-only مشتق) |
| 7 | فیلد `tax_included`؛ سیاست نمایش با مالیات فعال → D11 | قیمت ✓ «مالیات در صورت نیاز»، ADR-010 | kept (Q2، اصلاح‌شده) |
| 8 | availability in/low/out، بدون عدد؛ بدون InventoryItem → out | موجودی ✓ (Guest: وضعیت کلی)، ADR-005 | new |
| 9 | availability کلی محصول از تنوع‌ها | دسته‌بندی ✓ کارت «وضعیت موجودی» | new |
| 10 | خروجی: breadcrumb، attributes، options، variants، media | دسته‌بندی ✓ breadcrumb، معماری ✓ «تصاویر، تنوع‌ها، قیمت و موجودی» | new |
| 11 | `default_variant_id` و `price_range` | — | kept (تصمیم کاربر) |
| 12 | `/products/{id}/pricing` و `/availability` با id می‌مانند | قیمت ✓، موجودی ✓ | unchanged (Q3) |
| 13 | حذف POST/PATCH/DELETE `/products` قالبی | CLAUDE.md §10 | changed (removed) |
| 14 | ProductHistory حذف → AuditLog | هویت ✓ AuditLog | changed |
| 15 | ۱۲ endpoint admin (product، `/admin/product-variants/{id}`، media) | قالبی → `/admin`؛ مسیر variant از قیمت ✓؛ PLAN CAT-05/CAT-11 | changed/new |
| 16 | status draft/published/archived؛ گراف انتقال؛ `published_at` در اولین انتشار | PLAN CAT-02، دسته‌بندی ✓ (publishedAt، sort newest) | new (گراف: تصمیم من) |
| 17 | شرط انتشار: تنوع فعال با قیمت + تصویر اصلی؛ گارد آخرین تنوع/تصویر → 422 | PLAN CAT-11، معماری ✓ «قیمت معتبر» | new |
| 18 | slug: فرمت، ورود دستی، 409 `DUPLICATE_SLUG` | دسته‌بندی ✓ 409 slug، ADR-015 | new (فرمت: کم‌اثر) |
| 19 | SKU: فرمت، uppercase، partial unique → 409 | PLAN CAT-03، ADR-015 | new |
| 20 | VariantOption: color/size/model متن آزاد، ترکیب یکتا | معماری ✓ «رنگ، سایز/مدل»، PLAN CAT-04 | new |
| 21 | قیمت اولیه هنگام ایجاد تنوع با `pricing:update`؛ تغییر بعدی فقط `/price` | قیمت ✓ (pricing:update، PATCH .../price) | new |
| 22 | موجودی در این بخش ویرایش نمی‌شود | موجودی ✓، ADR-005 | new |
| 23 | حذف همیشه soft؛ cascade به تنوع‌ها؛ بدون restore در v1 | CLAUDE.md §8، معماری ✓، SD rule | kept (feature جدید اضافه نمی‌کند) |
| 24 | media: jpeg/png/webp، ۵MB، magic bytes، حذف EXIF، storage interface | ADR-009، معماری ✓ «آپلود عکس» | kept (Q4 + magic bytes + EXIF) |
| 25 | دقیقاً یک تصویر اصلی (partial unique) | PLAN CAT-05 «main image» | new |
| 26 | audit همه writeها با ۱۰ action | معماری ✓، دسته‌بندی ✓ AuditLog | new |
| 27 | RBAC `catalog:manage`؛ content_manager/support بدون دسترسی؛ قفل ردیف Product | seed/ADR-004، ADR-018 | new (قفل: تصمیم من) |

## Open questions (resolved 2026-10-09 → ADR-020)
- **Q1 (scope):** محصول منتشرشده در دسته غیرفعال: نمایش (پیشنهاد من) یا 404؟
- **Q2 (پول):** قیمت صفحه محصول بدون مالیات (پیشنهاد من، چون پیش‌فرض `tax_enabled=false`) یا شامل مالیات وقتی فعال است؟
- **Q3 (API):** `GET /products/{id}/pricing` و `/availability` با id بمانند (پیشنهاد من: بله، چون قرارداد بخش‌های ✓ است و slug فقط برای URL صفحه است)؟
- **Q4 (امنیت/scope):** media فقط تصویر، jpeg/png/webp، حداکثر ۵MB، بدون ویدئو در v1؟ (تشخیص نوع از محتوا احتمالاً یک dependency جدید در CAT-05 لازم دارد، مثل Pillow.)
- **SCOPE? دیگر:** `default_variant_id` و `price_range` بمانند یا حذف شوند؟ نظرات کاربران (معماری ✓ «نظرات کاربران») در هیچ بخشی تعریف نشده و در این پیش‌نویس نیست.

## Implementation Notes
- پیش‌نویس در commit `f84860f` (`docs/project/drafts/CAT-00-prd.diff`) است؛ بعد از apply حذف شد. فایل PRD با CRLF است.
- apply: `git apply docs/project/drafts/CAT-00-prd.diff`، سپس حذف فایل draft، ردیف DECISIONS، و commit جدا (`docs(prd): ...`) تا با `git revert` برگشت‌پذیر باشد.
- ستون‌های قیمت ProductVariant مال PRC-01 هستند. CAT-03 بدون قیمت ساخته می‌شود؛ قانون «تنوع فعال بدون قیمت → 422» بعد از PRC-01 فعال می‌شود.

## Risks · Rollback · Extra checks (HIGH)
- **ریسک:** تعارض با بخش‌های ✓؛ scope بیرون از PRD؛ تغییر قرارداد API (slug). کاهش: جدول خلاصه بالا و برچسب SCOPE?.
- **Rollback:** قبل از تأیید چیزی روی PRD اعمال نشده است. بعد از apply، یک commit جدا با `git revert` برمی‌گردد.
- **بررسی‌ها:** diff فقط سه بازه (خط 62، 1778–1982، 5886–6090) را تغییر می‌دهد؛ `git apply --check` موفق؛ pytest، ruff و mypy برای اطمینان از نبود تغییر کد.

## Validation
```powershell
git apply --check docs/project/drafts/CAT-00-prd.diff
python -m pytest -q   # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-10-09: plan تأیید شد (محل draft، SEC-06 بیرون از batch؛ تصمیم: public با slug، admin با id). پیش‌نویس و diff ساخته شد؛ `git apply --check` موفق. منتظر تأیید کاربر.
- 2026-10-09: تأیید کاربر. Q1: صفحه نمایش داده می‌شود و محصول از لیست دسته حذف می‌شود. Q2: فیلد `tax_included`؛ سیاست نمایش به D11. Q3: بله. Q4: بله، به‌علاوه magic bytes و حذف EXIF. SCOPE?: هر ۶ ردیف kept (هیچ‌کدام feature جدید کاربرمحور نبود؛ گزارش قبلی به‌اشتباه ۷ گفته بود). diff بازسازی و اعمال شد (byte به byte برابر پیش‌نویس)؛ «✓» روی دو بخش؛ D24/ADR-020 و ردیف PRD changes ثبت شد؛ CLAUDE.md §10 (۸ بخش مرجع، ۳۱ قالبی) به‌روز شد؛ draft حذف شد. COMPLETE.
