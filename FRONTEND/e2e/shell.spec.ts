import { expect, test } from "@playwright/test";

import { expectNoAxeViolations } from "./a11y";

test.describe("storefront shell", () => {
  test("renders RTL Persian with the shared header and dark footer, axe clean", async ({
    page,
  }) => {
    await page.goto("/");

    await expect(page.locator("html")).toHaveAttribute("lang", "fa");
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.getByRole("link", { name: "کالیا — صفحه‌ی اصلی" })).toBeVisible();
    await expect(page.getByRole("link", { name: "سبد خرید، ۰ کالا" })).toBeVisible();
    await expect(page.getByRole("contentinfo").getByText("KALÉA")).toBeVisible();

    await expectNoAxeViolations(page);
  });

  test("desktop shows the category nav from the API", async ({ page, isMobile }) => {
    test.skip(isMobile, "phone uses the menu");
    await page.goto("/");

    const nav = page.getByRole("navigation", { name: "دسته‌بندی‌ها" });
    await expect(nav.getByRole("link", { name: "کیف" })).toHaveAttribute("href", "/c/bags");
    await expect(nav.getByRole("link")).toHaveCount(4);
  });

  test("phone opens the category menu, axe clean while open", async ({ page, isMobile }) => {
    test.skip(!isMobile, "desktop shows the nav inline");
    await page.goto("/");

    const toggle = page.getByRole("button", { name: "منو" });
    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    const menu = page.getByRole("navigation", { name: "منوی اصلی" });
    await expect(menu.getByRole("link", { name: "زیورآلات" })).toBeVisible();
    await expectNoAxeViolations(page);

    await page.keyboard.press("Escape");
    await expect(menu).toBeHidden();
  });

  test("touch targets in the header are at least 44px", async ({ page }) => {
    await page.goto("/");
    const targets = page.locator("header a:visible, header button:visible");
    const count = await targets.count();
    expect(count).toBeGreaterThan(0);
    for (let index = 0; index < count; index += 1) {
      const box = await targets.nth(index).boundingBox();
      expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
    }
  });
});
