"use client";

import { useQuery } from "@tanstack/react-query";

import { useAuthStatus } from "@/auth/AuthProvider";

import { api } from "../client";
import { unwrap } from "../errors";
import type { components } from "../schema.gen";

export type Cart = components["schemas"]["CartResponse"];

export const cartKeys = {
  all: ["cart"] as const,
  current: (owner: "user" | "guest") => ["cart", owner] as const,
};

/**
 * The current cart, always as computed by the server. Waits until the auth state is known:
 * a guest request before the refresh settles would show the wrong cart.
 */
export function useCart() {
  const status = useAuthStatus();
  const owner = status === "authenticated" ? "user" : "guest";
  return useQuery({
    queryKey: cartKeys.current(owner),
    queryFn: () => unwrap(api.GET("/api/v1/cart")),
    enabled: status !== "unknown",
  });
}

/** Units in the cart, for the header badge. */
export function cartUnitCount(cart: Cart | undefined): number {
  return cart?.items.reduce((sum, line) => sum + line.quantity, 0) ?? 0;
}
