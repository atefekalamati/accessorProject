import type { Metadata, Viewport } from "next";

import "../../docs/design/design-system/tokens.css";
import "@/styles/globals.css";
import { fontVariables } from "@/styles/fonts";

import { Providers } from "./providers";

export const metadata: Metadata = {
  title: { default: "کالیا", template: "%s — کالیا" },
  description: "اکسسوری‌های پاستلی، فروخته‌شده مستقیم.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // = --surface in tokens.css. A <meta> value cannot reference a CSS variable; keep in sync.
  themeColor: "#F7F5FB",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fa" dir="rtl" className={fontVariables}>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
