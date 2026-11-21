import type { components } from "../../src/api/schema.gen";

type Schemas = components["schemas"];

/** Sample data typed against the contract; a schema change breaks these at compile time. */

export const categoryTree: Schemas["CategoryTreeResponse"] = {
  items: [
    {
      id: "0b8f7c52-8f39-4d4e-9d11-2f0f0b3d1a01",
      title: "کیف",
      slug: "bags",
      icon_key: null,
      image_url: null,
      children: [],
    },
    {
      id: "0b8f7c52-8f39-4d4e-9d11-2f0f0b3d1a02",
      title: "زیورآلات",
      slug: "jewelry",
      icon_key: null,
      image_url: null,
      children: [],
    },
    {
      id: "0b8f7c52-8f39-4d4e-9d11-2f0f0b3d1a03",
      title: "شال و روسری",
      slug: "scarves",
      icon_key: null,
      image_url: null,
      children: [],
    },
    {
      id: "0b8f7c52-8f39-4d4e-9d11-2f0f0b3d1a04",
      title: "اکسسوری مو",
      slug: "hair-accessories",
      icon_key: null,
      image_url: null,
      children: [],
    },
  ],
};

export const emptyCart: Schemas["CartResponse"] = {
  items: [],
  subtotal: 0,
  product_discount_total: 0,
  discount_code_amount: 0,
  tax_amount: 0,
  shipping_amount: 0,
  grand_total: 0,
  currency: "TOMAN",
  calculated_at: "2026-11-20T08:00:00Z",
  discount: null,
  has_changes: false,
};

export function cartLine(
  overrides: Partial<Schemas["CartLineResponse"]> = {},
): Schemas["CartLineResponse"] {
  return {
    id: "6a0f3f3e-1b7d-4a55-8a3c-111111111111",
    variant_id: "6a0f3f3e-1b7d-4a55-8a3c-222222222222",
    product_id: "6a0f3f3e-1b7d-4a55-8a3c-333333333333",
    product_title: "کیف کوچک یاسی",
    product_slug: "small-lilac-bag",
    sku: "BAG-LILAC-S",
    options: { color: "یاسی" },
    quantity: 1,
    available: true,
    stock_status: "ok",
    unit_price: { original: 1_200_000, final: 980_000 },
    subtotal: 1_200_000,
    product_discount: 220_000,
    code_discount: 0,
    tax: 0,
    total: 980_000,
    price_changed: false,
    previous_unit_price: null,
    ...overrides,
  };
}

export function cartWith(lines: Schemas["CartLineResponse"][]): Schemas["CartResponse"] {
  return { ...emptyCart, items: lines };
}

export const tokenResponse: Schemas["TokenResponse"] = {
  access_token: "test-access-token",
  token_type: "bearer",
  expires_in_seconds: 900,
};

export function errorBody(code: string, details: unknown[] = []): Schemas["ErrorResponse"] {
  return {
    error: { code, message: code, details },
    request_id: "5d1c4c1e-0000-4000-8000-000000000000",
  };
}
