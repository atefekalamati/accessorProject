import "server-only";

import { headers } from "next/headers";
import createClient from "openapi-fetch";

import { clientIpFrom } from "@/server/client-ip";
import { apiOrigin, trustedProxyHops } from "@/server/env";

import type { paths } from "./schema.gen";

/** Upper bound for one server-side API call; a hung API must not hang every page. */
export const SERVER_FETCH_TIMEOUT_MS = 5_000;

/**
 * API client for Server Components: public endpoints only (the access token lives in the
 * browser). Prices and stock must be fresh, so nothing is cached. The visitor's IP is
 * forwarded so per-IP limits do not count every visitor as this server.
 */
export async function serverApi() {
  const incoming = await headers();
  const ip = clientIpFrom(incoming.get("x-forwarded-for"), trustedProxyHops());
  return createClient<paths>({
    baseUrl: apiOrigin(),
    cache: "no-store",
    headers: ip === null ? {} : { "x-forwarded-for": ip, "x-real-ip": ip },
  });
}
