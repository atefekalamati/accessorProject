import localFont from "next/font/local";

/**
 * Self-hosted fonts (no request to Google at build or run time). Vazirmatn ships as two
 * subsets with separate families so each keeps its glyph range; `--font-sans` lists both.
 */

export const vazirmatnArabic = localFont({
  src: "../../node_modules/@fontsource-variable/vazirmatn/files/vazirmatn-arabic-wght-normal.woff2",
  weight: "300 700",
  style: "normal",
  display: "swap",
  variable: "--font-vazirmatn-arabic",
  fallback: ["system-ui", "sans-serif"],
});

export const vazirmatnLatin = localFont({
  src: "../../node_modules/@fontsource-variable/vazirmatn/files/vazirmatn-latin-wght-normal.woff2",
  weight: "300 700",
  style: "normal",
  display: "swap",
  variable: "--font-vazirmatn-latin",
  fallback: ["system-ui", "sans-serif"],
});

/** Footer wordmark only («KALÉA»). */
export const cormorant = localFont({
  src: "../../node_modules/@fontsource/cormorant-garamond/files/cormorant-garamond-latin-500-normal.woff2",
  weight: "500",
  style: "normal",
  display: "swap",
  preload: false,
  variable: "--font-cormorant",
  fallback: ["Georgia", "serif"],
});

export const fontVariables = [vazirmatnArabic, vazirmatnLatin, cormorant]
  .map((font) => font.variable)
  .join(" ");
