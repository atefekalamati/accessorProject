# KALÉA Frontend Handoff

Design source of truth for the KALÉA (کالیا) storefront frontend. Read this file first, then `design-system/README.md`.

Precedence when sources disagree: **backend `openapi.json` > `FRONTEND.md` / PRD in the repo > this package**. These designs define look, copy and states. They do not define API contracts.

## 1. Package contents

| Path | What it is |
|---|---|
| `design/pages/*.dc.html` | 12 approved screens. Plain HTML with inline styles plus a small template layer (see §6). Read them as visual and markup specs; do not ship them. |
| `design-system/README.md` | Brand book: voice, color rules, components, logo, accessibility. |
| `design-system/tokens.json` | Design tokens: 20 colors, type scale, spacing, radius. |
| `design-system/tokens.css` | The same tokens as CSS custom properties plus `.t-*` type classes (generated from tokens.json). |
| `brand/kalea-ribbon.png` | Primary logo with a transparent background, 900×348 px (ratio about 2.6:1). |
| `brand/kalea-ribbon-light.png` | Light, single-color logo for rare dark placements. |
| `CLAUDE-CODE-PROMPT.md` | Kick-off prompt for the frontend session. |

## 2. Global rules

- **Language and direction.** Persian. `<html lang="fa" dir="rtl">`. Phone numbers, OTP codes and order numbers render `direction: ltr` inside RTL text.
- **Digits and money.**
  - Show Persian digits (۰–۹) in the UI.
  - Money is an integer in Toman, shown as «۱۲۳٬۰۰۰ تومان» with no decimals.
  - Convert digits only at render time. Keep raw integers in state.
- **Pricing.** The backend owns all prices, discounts, shipping and totals. The frontend never computes a payable amount; it displays what the API returns. Cart and checkout totals always come from the server.
- **Stock.** Show status only: «موجود», «تعداد محدود», «ناموجود». Never show a stock count.
- **Fonts.**
  - Vazirmatn (300–700) for all text.
  - Cormorant Garamond 500, uppercase, letter-spacing 0.06em, only for the footer wordmark «KALÉA».
- **Logo.**
  - `brand/kalea-ribbon.png` in every header: 64px tall on desktop, 44–48px on phone, 56px on login screens.
  - Always link it to `/`, with `aria-label="کالیا — صفحه‌ی اصلی"` and `alt="Kaléa"`.
  - The footer uses the text wordmark, not the image.
  - No tagline under the logo.
- **Layout.** Max content width 1280px. Gutters are 32px on desktop and 16px on phone. Product grids use `repeat(auto-fill, minmax(240px, 1fr))`.
- **Shape.** Rounded everywhere: radius 14 / 16 / 24 / 28 px and pill. No shadows, gradients or left-border cards.
- **Accessibility.**
  - Touch targets are at least 44px.
  - Use real `<button>`, `<a>`, and `<input>` with a `<label>`.
  - Icon-only buttons get an `aria-label`.
  - Text contrast is at least 4.5:1.
  - Notices use `role="status"` (informational) or `role="alert"` (blocking).
- **Icons.** Inline stroke SVG on a 24px grid, stroke 1.6, `currentColor`, `aria-hidden="true"`. No emoji.

## 3. Key tokens (full list in tokens.json)

| Token | Hex | Use |
|---|---|---|
| `surface` | #F7F5FB | Page background |
| `surface-card` | #FFFFFF | Cards, panels, inputs |
| `lilac-100` / `lilac-200` | #ECE6F6 / #E7E0F3 | Icon buttons, info notice / hero, image fields |
| `mint-200` / `mint-300` | #DDF0E8 / #CDEBDD | Success notices / cart badge |
| `blush-200` | #F3E2EC | Error and unavailable notices |
| `cream-200` | #FBF0D9 | Decorative image fields |
| `neutral-100` | #EFEDF3 | Disabled, out of stock |
| `line` | #E1DAEA | Borders, hairlines |
| `ink` / `ink-muted` | #2E2A3A / #5F5A6E | Text; footer background / secondary text |
| `accent` / `on-accent` | #6B4FA0 / #FFFFFF | The one primary action per view, links, selected states, discount badge |
| `success` / `danger` | #3E7060 / #8A3B5C | In-stock text / error text |
| `on-ink`, `on-ink-muted`, `wordmark-on-ink` | #ECE8F4, #B8B2C7, #ECE8F4 | Footer |

Pastels are backgrounds, never text colors.

## 4. Screens

Suggested routes; adjust them to the router you choose. Desktop artboards are 1440px wide; phone artboards are 390px.

| Design file | Route | Viewport | What it must show |
|---|---|---|---|
| `Lilac.dc.html` | `/` | desktop | Header (logo, category nav, search/account/cart icon buttons with cart count); lilac hero «رنگ‌های آرام برای روزهای قشنگ»; «دسته‌بندی‌ها» tiles (bags, jewelry, scarves, hair accessories); «تازه‌ها» product cards; seasonal band «رنگ‌های آرام فصل»; brand promises (خرید مستقیم، کیفیت انتخاب‌شده، پرداخت امن); dark footer with the text wordmark. |
| `HomeMobile.dc.html` | `/` | phone | Same content stacked; two-column product grid. |
| `Category.dc.html` | `/c/[slug]` | desktop, interactive | Filter sidebar: color (multi-select chips), status (in stock only), sale only, price range «از / تا». Sort: newest, best selling, price ascending, price descending. Active-filter chips with × and «پاک کردن همه»; result count; empty state «محصولی با این فیلترها پیدا نشد» with «پاک کردن فیلترها». Phone: the sidebar collapses (a phone category design is not drawn yet; see §7). |
| `Product.dc.html` | `/p/[slug]` | desktop, interactive | Gallery; name, price, struck old price, discount badge; color swatches (aria-pressed; out-of-stock swatch dimmed and still selectable, then it shows «این رنگ فعلاً ناموجود» and disables add); stock status dot and text; quantity stepper 1–10; «افزودن به سبد»; a note that the final price, code and shipping are computed in the cart; accordions (description, material and size, shipping). |
| `ProductMobile.dc.html` | `/p/[slug]` | phone | Same; sticky bottom bar with stepper and «افزودن به سبد». |
| `Cart.dc.html` | `/cart` | desktop | Step chips (1 cart, 2 address, 3 payment). Line states: normal; **price changed** (lilac notice: old → new price, «متوجه شدم» to acknowledge); **unavailable** (blush alert, excluded from the total, «حذف از سبد»). Discount code field with «اعمال». Summary: items, discount, shipping «مرحله‌ی بعد», payable. «ادامه: آدرس و ارسال» stays disabled while any line is unavailable, with the reason shown («اول کالای ناموجود را حذف کن»). Whether an unacknowledged price change also blocks checkout follows the API. |
| `CartMobile.dc.html` | `/cart` | phone | Same; sticky bottom total and button. |
| `Checkout.dc.html` | `/checkout` | desktop | Address radio cards (default badge, «+ افزودن آدرس جدید»); shipping method radios with ETA and cost; free-shipping note; order summary; the 15-minute reservation notice; «ثبت سفارش و پرداخت آنلاین». |
| `CheckoutMobile.dc.html` | `/checkout` | phone | Same; collapsible summary; sticky pay button. |
| `Orders.dc.html` | `/account/orders` | desktop | Order list: number `ORD-YYYY-NNNNNN` (LTR), date, status pill («در انتظار پرداخت», «لغو شده», …), total; actions «ادامه‌ی پرداخت» and «لغو سفارش» only where the status allows. |
| `LoginPhone.dc.html` | `/login` | phone | «ورود یا ثبت‌نام»: phone input (LTR, `inputmode="numeric"`, `autocomplete="tel"`), primary button. |
| `LoginCode.dc.html` | `/login/verify` | phone | 6-digit code input (`autocomplete="one-time-code"`), resend with countdown, edit-number link, error «کد درست نیست یا منقضی شده. دوباره امتحان کن.» on blush. |

Product names, images and prices in the designs are samples or `[placeholders]`. Real data comes from the API.

## 5. States every data screen needs

Loading (skeletons in the card shapes, no spinners in place of layout), empty, error (blush notice plus retry), and disabled actions that state their reason in text. Payment buttons and order submit must be safe against double clicks: disable while pending and send the idempotency key the API requires (check `openapi.json`).

## 6. Reading the `.dc.html` files

They are normal HTML with inline styles, which is the exact spec for spacing, color and size. Extra syntax to ignore or translate:

- `<x-dc>` is the root wrapper and `<helmet>` holds fonts and base CSS.
- `{{name}}` is a value from the script block at the bottom.
- `<sc-if value=…>` is a condition and `<sc-for list=… as=…>` is a loop.
- `class Component extends DCLogic { renderVals() … }` holds the sample data and interaction logic. `Category` (filter and sort) and `Product` (color, quantity, add to cart) contain logic worth reading.
- `href="X.dc.html"` links mark the navigation flow between screens.

To view them as live, clickable designs, open the KALÉA — Final Design canvas in Claude and use Play.

## 7. Not designed yet

- Category page on phone (filters in a bottom sheet is the intended pattern).
- Payment result pages (success and failed or cancelled, with the order number and next step).
- Address form (add and edit).
- 404 and server-error pages.

Build these from the tokens and the patterns above, and keep them consistent with the drawn screens.
