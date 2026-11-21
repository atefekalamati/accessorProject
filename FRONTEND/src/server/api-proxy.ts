import { clientIpFrom } from "./client-ip";

/**
 * Same-origin proxy: /api/v1/* on this server → the same path on API_ORIGIN.
 *
 * - Request headers pass through an allowlist; client-supplied X-Forwarded-For / X-Real-IP
 *   are replaced (never appended) by the one client IP we resolved.
 * - Every Set-Cookie of the API is passed back unchanged (refresh_token, cart_token).
 * - Redirects are not followed; the browser sees them.
 */

export const API_PREFIX = "/api/v1/";
/** The API rejects bodies over 1 MiB (SEC-02); refuse them here before buffering more. */
export const MAX_BODY_BYTES = 1_048_576;
const UPSTREAM_TIMEOUT_MS = 30_000;

const FORWARDED_REQUEST_HEADERS = [
  "accept",
  "accept-language",
  "authorization",
  "content-type",
  "cookie",
  "idempotency-key",
  "if-none-match",
  "user-agent",
  "x-request-id",
] as const;

const DROPPED_RESPONSE_HEADERS = new Set([
  "connection",
  "keep-alive",
  "transfer-encoding",
  "upgrade",
  "trailer",
  "proxy-authenticate",
  // fetch() already decoded the body, so the original encoding and length are wrong.
  "content-encoding",
  "content-length",
  // Re-added one by one below; Headers would otherwise join them with a comma.
  "set-cookie",
]);

export interface ProxyOptions {
  origin: string;
  hops: number;
  fetchImpl?: typeof fetch;
}

export async function proxyToApi(request: Request, options: ProxyOptions): Promise<Response> {
  const incoming = new URL(request.url);
  if (!isSafeApiPath(incoming.pathname)) {
    return errorResponse(404, "NOT_FOUND", "Not found");
  }

  const body = await readBody(request);
  if (body === "too_large") {
    return errorResponse(413, "PAYLOAD_TOO_LARGE", "Request body is too large");
  }

  const headers = new Headers();
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value !== null) headers.set(name, value);
  }
  const ip = clientIpFrom(request.headers.get("x-forwarded-for"), options.hops);
  if (ip !== null) {
    headers.set("x-forwarded-for", ip);
    headers.set("x-real-ip", ip);
  }

  const target = `${options.origin}${incoming.pathname}${incoming.search}`;
  const fetchImpl = options.fetchImpl ?? fetch;
  let upstream: Response;
  try {
    upstream = await fetchImpl(target, {
      method: request.method,
      headers,
      body,
      redirect: "manual",
      cache: "no-store",
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    });
  } catch (error) {
    const timedOut = error instanceof DOMException && error.name === "TimeoutError";
    return timedOut
      ? errorResponse(504, "UPSTREAM_TIMEOUT", "The API did not answer in time")
      : errorResponse(502, "UPSTREAM_UNAVAILABLE", "The API is not reachable");
  }

  const responseHeaders = new Headers();
  upstream.headers.forEach((value, name) => {
    if (!DROPPED_RESPONSE_HEADERS.has(name.toLowerCase())) responseHeaders.set(name, value);
  });
  for (const cookie of upstream.headers.getSetCookie()) {
    responseHeaders.append("set-cookie", cookie);
  }
  // A redirect from the API (e.g. FastAPI's trailing-slash 307) names the internal origin;
  // make it relative so the browser stays on this origin and the origin is not exposed.
  const location = upstream.headers.get("location");
  if (location !== null) responseHeaders.set("location", relativeTo(options.origin, location));

  const bodyless = upstream.status === 204 || upstream.status === 304 || request.method === "HEAD";
  return new Response(bodyless ? null : upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  });
}

/** Only /api/v1/…, with no dot segments, encoded dots or slashes, or backslashes. */
export function isSafeApiPath(pathname: string): boolean {
  if (!pathname.startsWith(API_PREFIX)) return false;
  if (/%2e|%2f|%5c|\\/i.test(pathname)) return false;
  return !pathname.split("/").some((segment) => segment === "." || segment === "..");
}

async function readBody(
  request: Request,
): Promise<Uint8Array<ArrayBuffer> | undefined | "too_large"> {
  if (request.method === "GET" || request.method === "HEAD") return undefined;
  const declared = Number(request.headers.get("content-length") ?? "0");
  if (declared > MAX_BODY_BYTES) return "too_large";
  if (request.body === null) return undefined;

  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > MAX_BODY_BYTES) {
      await reader.cancel();
      return "too_large";
    }
    chunks.push(value);
  }
  if (size === 0) return undefined;
  const buffer = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    buffer.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return buffer;
}

/** `location` without the API origin when it points at the API; otherwise unchanged. */
export function relativeTo(origin: string, location: string): string {
  let url: URL;
  try {
    url = new URL(location, origin);
  } catch {
    return location;
  }
  return url.origin === origin ? `${url.pathname}${url.search}${url.hash}` : location;
}

/** Same shape as the API's ErrorResponse, so the client handles it the same way. */
function errorResponse(status: number, code: string, message: string): Response {
  const requestId = crypto.randomUUID();
  return Response.json(
    { error: { code, message, details: [] }, request_id: requestId },
    { status, headers: { "cache-control": "no-store", "x-request-id": requestId } },
  );
}
