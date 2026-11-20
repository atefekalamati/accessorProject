# Kaléa

Kaléa (کالیا) is a Persian, right-to-left online store for pastel fashion accessories — bags, jewelry, scarves and hair accessories — sold directly, without intermediaries. The look is soft and girly but calm: pastel grounds, dark ink text, one violet accent, generous rounded corners.

## Content fundamentals

- **Language and direction.** All UI copy is Persian, `dir="rtl"`. Phone numbers, OTP codes and order numbers (`ORD-YYYY-NNNNNN`) are set `direction: ltr` inside RTL text.
- **Voice.** Warm and direct, second person singular («تو»): «شماره‌ی موبایلت را وارد کن»، «برای ادامه، کالای ناموجود را حذف کن». Short sentences, no exclamation marks, no slang.
- **Digits.** Persian digits (۰–۹) in UI text. Money is integer Toman, written «[مبلغ] تومان» with no decimals.
- **Brand promises** (use these words, invent no others): خرید مستقیم، کیفیت انتخاب‌شده، پرداخت امن.
- **Never** show an exact stock count to customers; show status only.

## Visual foundations

- **Ground.** Every page sits on `surface`. White `surface-card` holds products, cart lines and panels.
- **Pastels are grounds, never text.** `lilac-200`, `mint-200`, `blush-200`, `cream-200` fill images, tiles and notices. All text on them is `ink` or `ink-muted` (both pass 4.5:1 on every pastel).
- **One accent.** `accent` marks the single primary action per view, discount badges, links and selected states. Text on it is `on-accent`.
- **Meaning by pastel.** `mint-200` = positive (added to cart, code applied, free shipping); `lilac-100` = informational (price changed); `blush-200` = problem (item unavailable, wrong code), with `danger` text.
- **Shape.** Rounded everywhere: `radius-lg` cards, `radius-xl` heroes, `radius-pill` badges. No hairline-left cards, no gradients, no shadows.
- **Type.** `Vazirmatn` for all Persian text; headings 700, body 400 at 1.8 line height. `Cormorant Garamond` upright 500 (uppercase «KALÉA», letter-spacing 0.06em) is used ONLY for the footer wordmark; see Logo.
- **Layout.** Max content width 1280px, `space-8` desktop gutters, `space-4` on phones; sections separated by `space-24`. Grids use `repeat(auto-fill, minmax(240–250px, 1fr))` so they collapse to two columns on phones.

## Logo

- **Primary logo (header).** The ribbon logo: serif «KALÉA» in warm brown with a blush ribbon woven through it, transparent PNG, ratio ≈ 2.6:1. Asset: `brand/kalea-ribbon.png` (`kalea-ribbon.png`). Height 64px on desktop headers, 44–48px on phone headers, 56px on login screens. Always a link to home with `aria-label="کالیا — صفحه‌ی اصلی"` and `alt="Kaléa"`. Never recolor, stretch, crop or add a tagline under it.
- **Footer wordmark.** On `ink` grounds use text, not the image: «KALÉA» in `Cormorant Garamond` 500, uppercase, letter-spacing 0.06em, color `wordmark-on-ink`, 26–36px.
- **Light mono logo.** A single-color light version exists for rare dark placements: `brand/kalea-ribbon-light.png` (`kalea-ribbon-light.png`). The footer still uses the text wordmark.
- **Clear space.** Keep at least the height of the «A» free around the logo; minimum height 32px.

## Components (as drawn on the storefront canvas)

- **Product card.** `surface-card`, `radius-lg`, `space-3` padding; square image at radius 18px; name (body 500), price (body-strong), color dots. Badges top-right: «تازه» white pill, discount `accent` pill with `on-accent`.
- **Stock status** (from the API, never a number): «موجود» `success`, «تعداد محدود» `accent` on `lilac-100`, «ناموجود» `ink-muted` with the image on `neutral-100` and the add button disabled.
- **Buttons.** Primary: `accent` fill, `radius-md`, min height 52px (48px in heroes). Secondary: `surface-card` with `line` border, `radius-sm`. Icon buttons 44×44, `lilac-100`, `radius-sm`, always with `aria-label`.
- **Cart line flags.** Price changed → `lilac-100` notice with old/new price and «متوجه شدم» (acknowledge). Unavailable → `blush-200` notice, excluded from totals, checkout disabled until removed.
- **Step chips.** Current step `accent` pill; done `mint-200` with ✓; upcoming `lilac-100`.

## Iconography

Inline stroke SVG on a 24px grid, stroke width 1.4–1.6, round shapes, `currentColor`. Decorative icons get `aria-hidden="true"`. No emoji, no filled icon sets.

## Accessibility

Touch targets ≥44px. Real `<button>`, `<a>`, `<input>` with `<label>`. Text contrast ≥4.5:1 on its ground; colors that carry meaning also differ in lightness and are always paired with words.
