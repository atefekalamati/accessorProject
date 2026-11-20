import { describe, expect, it } from "vitest";

import { formatDate, formatNumber, formatToman, toAsciiDigits, toPersianDigits } from "./format";

describe("format", () => {
  it("converts digits to Persian and keeps other characters", () => {
    expect(toPersianDigits(1405)).toBe("۱۴۰۵");
    expect(toPersianDigits("ORD-2026-000123")).toBe("ORD-۲۰۲۶-۰۰۰۱۲۳");
  });

  it("converts Persian and Arabic-Indic digits back to ASCII", () => {
    expect(toAsciiDigits("۰۹۱۲۳۴۵۶۷۸۹")).toBe("09123456789");
    expect(toAsciiDigits("٠١٢٣٤٥")).toBe("012345");
    expect(toAsciiDigits("12۳۴")).toBe("1234");
  });

  it("formats integers with Persian digits and the Persian thousands separator", () => {
    expect(formatNumber(123000)).toBe("۱۲۳٬۰۰۰");
    expect(formatNumber(0)).toBe("۰");
  });

  it("formats Toman amounts without decimals", () => {
    expect(formatToman(1_250_000)).toBe("۱٬۲۵۰٬۰۰۰ تومان");
  });

  it("formats dates in the Jalali calendar, Tehran time", () => {
    // 2026-11-20 21:00 UTC is already 21 Nov (30 Aban 1405) in Tehran (+03:30).
    expect(formatDate("2026-11-20T21:00:00Z")).toBe("۳۰ آبان ۱۴۰۵");
  });
});
