import "server-only";

/** Server-only settings; read lazily so `next build` works without them. */

export function apiOrigin(): string {
  const raw = process.env.API_ORIGIN;
  if (!raw) throw new Error("API_ORIGIN is not set");
  const url = new URL(raw);
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error("API_ORIGIN must be an http(s) origin");
  }
  return url.origin;
}

export function trustedProxyHops(): number {
  const raw = process.env.TRUSTED_PROXY_HOPS ?? "0";
  const hops = Number(raw);
  if (!Number.isInteger(hops) || hops < 0 || hops > 10) {
    throw new Error("TRUSTED_PROXY_HOPS must be an integer from 0 to 10");
  }
  return hops;
}

export function fakeGatewayPageEnabled(): boolean {
  return process.env.FAKE_GATEWAY_PAGE === "1";
}
