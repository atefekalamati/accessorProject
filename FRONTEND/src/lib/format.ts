/**
 * Render-time formatting (HANDOFF §2): Persian digits, «… تومان», Jalali dates. State
 * always keeps raw integers and ISO strings; convert only when rendering.
 */

const PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹";
const numberFormat = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 0 });
const dateFormat = new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
  timeZone: "Asia/Tehran",
  year: "numeric",
  month: "long",
  day: "numeric",
});
const dateTimeFormat = new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
  timeZone: "Asia/Tehran",
  year: "numeric",
  month: "long",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

/** ASCII digits → Persian digits; everything else is kept (e.g. ORD-2026-000123). */
export function toPersianDigits(value: string | number): string {
  return String(value).replace(/[0-9]/g, (digit) => PERSIAN_DIGITS[Number(digit)]!);
}

/** Persian and Arabic-Indic digits → ASCII, for values sent to the API (e.g. OTP code). */
export function toAsciiDigits(value: string): string {
  return value
    .replace(/[۰-۹]/g, (digit) => String(digit.charCodeAt(0) - 0x06f0))
    .replace(/[٠-٩]/g, (digit) => String(digit.charCodeAt(0) - 0x0660));
}

/** 123000 → «۱۲۳٬۰۰۰». */
export function formatNumber(value: number): string {
  return numberFormat.format(value);
}

/** 123000 → «۱۲۳٬۰۰۰ تومان». The amount always comes from the API. */
export function formatToman(amount: number): string {
  return `${formatNumber(amount)} تومان`;
}

/** ISO timestamp → Jalali date in Tehran time, e.g. «۲۹ آبان ۱۴۰۵». */
export function formatDate(iso: string): string {
  return dateFormat.format(new Date(iso));
}

/** ISO timestamp → Jalali date and time in Tehran time. */
export function formatDateTime(iso: string): string {
  return dateTimeFormat.format(new Date(iso));
}
