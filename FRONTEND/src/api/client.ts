import createClient from "openapi-fetch";

import { REFRESH_MARGIN_MS, RefreshUnavailableError, refreshAccessToken } from "@/auth/refresh";
import { hasSessionHint } from "@/auth/session-hint";
import { getSession, isFresh } from "@/auth/token-store";

import type { paths } from "./schema.gen";

/** Auth endpoints that must never carry a Bearer token or trigger a refresh. */
const NO_BEARER_PATHS = new Set([
  "/api/v1/auth/request-otp",
  "/api/v1/auth/verify-otp",
  "/api/v1/auth/refresh",
  "/api/v1/auth/logout",
]);

/**
 * fetch with the access token: refreshes first when the token is about to expire, and on a
 * 401 waits for the shared refresh and retries once with the new token.
 *
 * A signed-in request never silently becomes a guest request (it would write to a guest
 * cart): when the session ended, the original 401 is returned; when the session could not
 * be checked (network, 5xx), a 503 SESSION_UNAVAILABLE is returned instead of sending it.
 */
export async function authFetch(request: Request): Promise<Response> {
  const path = new URL(request.url).pathname;
  if (NO_BEARER_PATHS.has(path)) return fetch(request);

  const retry = request.clone();
  const token = await currentToken();
  if (token === UNAVAILABLE) return sessionUnavailable();
  if (token !== null) request.headers.set("authorization", `Bearer ${token}`);
  const response = await fetch(request);
  if (response.status !== 401 || token === null) return response;

  let fresh: string | null;
  try {
    // Pass the token that was rejected: if another rotation already replaced it, the new
    // token is reused instead of rotating again.
    fresh = await refreshAccessToken(token);
  } catch (error) {
    if (error instanceof RefreshUnavailableError) return response;
    throw error;
  }
  if (fresh === null) return response;
  retry.headers.set("authorization", `Bearer ${fresh}`);
  return fetch(retry);
}

const UNAVAILABLE = Symbol("session-unavailable");

/** The token to send: null for a guest, UNAVAILABLE when a session could not be checked. */
async function currentToken(): Promise<string | null | typeof UNAVAILABLE> {
  const session = getSession();
  if (isFresh(session, REFRESH_MARGIN_MS)) return session!.token;
  if (session === null && !hasSessionHint()) return null;
  try {
    return await refreshAccessToken(session?.token ?? null);
  } catch (error) {
    if (error instanceof RefreshUnavailableError) return UNAVAILABLE;
    throw error;
  }
}

function sessionUnavailable(): Response {
  return Response.json(
    {
      error: { code: "SESSION_UNAVAILABLE", message: "Session check failed", details: [] },
      request_id: "",
    },
    { status: 503, headers: { "cache-control": "no-store" } },
  );
}

/**
 * Browser client: same-origin /api/v1/* through the proxy. Not for server code (the module
 * is evaluated during SSR of client components, but queries only run in the browser).
 */
export const api = createClient<paths>({
  baseUrl: typeof window === "undefined" ? "" : window.location.origin,
  fetch: authFetch,
});
