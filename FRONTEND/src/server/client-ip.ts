import { isIP } from "node:net";

/**
 * The client IP to forward to the API, from the X-Forwarded-For list Next.js hands us.
 *
 * Next.js sets X-Forwarded-For to the socket address only when the header is absent
 * (`??=`), so any value can come from the client itself. Only entries appended by trusted
 * proxies in front of this server can be believed: each appends the address of its peer, so
 * with `hops` trusted proxies the client is the `hops`-th entry from the right.
 *
 * With 0 hops nothing is trustworthy and null is returned: the API then sees this server's
 * address for every visitor (one shared rate-limit bucket), which is safe, never spoofable
 * (OPS-04). Also null when the list is too short or the entry is not an IP address.
 */
export function clientIpFrom(forwardedFor: string | null, hops: number): string | null {
  if (hops < 1 || !forwardedFor) return null;
  const entries = forwardedFor
    .split(",")
    .map((entry) => entry.trim())
    .filter((entry) => entry.length > 0);
  const index = entries.length - hops;
  if (index < 0) return null;
  const candidate = stripIpv4MappedPrefix(entries[index] ?? "");
  return isIP(candidate) === 0 ? null : candidate;
}

function stripIpv4MappedPrefix(address: string): string {
  const mapped = /^::ffff:(\d{1,3}(?:\.\d{1,3}){3})$/i.exec(address);
  return mapped?.[1] ?? address;
}
