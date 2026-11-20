import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { cartLine, cartWith } from "../../../test/msw/fixtures";
import { http } from "../../../test/msw/handlers";
import { server } from "../../../test/msw/server";
import { renderWithProviders } from "../../../test/render";

import { SiteHeader } from "./SiteHeader";

const pathname = vi.hoisted(() => ({ current: "/" }));
vi.mock("next/navigation", () => ({ usePathname: () => pathname.current }));

const categories = [
  { title: "کیف", slug: "bags" },
  { title: "زیورآلات", slug: "jewelry" },
];

beforeEach(() => {
  pathname.current = "/";
});

describe("SiteHeader", () => {
  it("links the logo home with the brand label", () => {
    renderWithProviders(<SiteHeader categories={categories} />);
    expect(screen.getByRole("link", { name: "کالیا — صفحه‌ی اصلی" })).toHaveAttribute("href", "/");
    expect(screen.getByAltText("Kaléa")).toBeInTheDocument();
  });

  it("lists categories and marks the current one", () => {
    pathname.current = "/c/jewelry";
    renderWithProviders(<SiteHeader categories={categories} />);

    const nav = screen.getByRole("navigation", { name: "دسته‌بندی‌ها" });
    expect(within(nav).getByRole("link", { name: "کیف" })).not.toHaveAttribute("aria-current");
    expect(within(nav).getByRole("link", { name: "زیورآلات" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("does not offer search (post-MVP)", () => {
    renderWithProviders(<SiteHeader categories={categories} />);
    expect(screen.queryByRole("button", { name: "جست‌وجو" })).not.toBeInTheDocument();
    expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
  });

  it("shows the server cart's unit count with Persian digits", async () => {
    server.use(
      http.get("/api/v1/cart", ({ response }) =>
        response(200).json(
          cartWith([cartLine({ quantity: 2 }), cartLine({ id: "x", quantity: 1 })]),
        ),
      ),
    );
    renderWithProviders(<SiteHeader categories={categories} />);

    expect(await screen.findByRole("link", { name: "سبد خرید، ۳ کالا" })).toHaveAttribute(
      "href",
      "/cart",
    );
  });

  it("labels an empty cart with zero and shows no badge", async () => {
    renderWithProviders(<SiteHeader categories={categories} />);
    const cart = await screen.findByRole("link", { name: "سبد خرید، ۰ کالا" });
    expect(cart.textContent).toBe("");
  });

  it("opens and closes the phone menu with aria-expanded and Escape", async () => {
    const user = userEvent.setup();
    renderWithProviders(<SiteHeader categories={categories} />);
    const toggle = screen.getByRole("button", { name: "منو" });

    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(toggle).toHaveAccessibleName("بستن منو");
    const menu = screen.getByRole("navigation", { name: "منوی اصلی" });
    expect(within(menu).getByRole("link", { name: "حساب کاربری" })).toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(toggle).toHaveFocus();
  });
});
