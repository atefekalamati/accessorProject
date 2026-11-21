import { describe, expect, it } from "vitest";

import { clientIpFrom } from "./client-ip";

describe("clientIpFrom", () => {
  it("returns null without a header", () => {
    expect(clientIpFrom(null, 0)).toBeNull();
    expect(clientIpFrom("", 1)).toBeNull();
  });

  it("trusts nothing with 0 hops (the client may have written the header itself)", () => {
    expect(clientIpFrom("203.0.113.7", 0)).toBeNull();
    expect(clientIpFrom("6.6.6.6, 203.0.113.7", 0)).toBeNull();
  });

  it("takes the hops-th entry from the right, ignoring forged entries on the left", () => {
    // Client forged "1.1.1.1"; the trusted ingress appended the real peer 198.51.100.4.
    expect(clientIpFrom("1.1.1.1, 198.51.100.4", 1)).toBe("198.51.100.4");
    // Two trusted proxies: outer appended the client, inner appended the outer proxy.
    expect(clientIpFrom("1.1.1.1, 198.51.100.4, 10.0.0.2", 2)).toBe("198.51.100.4");
  });

  it("returns null when the list is shorter than the trusted hops", () => {
    expect(clientIpFrom("198.51.100.4", 2)).toBeNull();
  });

  it("rejects entries that are not IP addresses", () => {
    expect(clientIpFrom("unknown", 1)).toBeNull();
    expect(clientIpFrom("198.51.100.4:443", 1)).toBeNull();
  });

  it("accepts IPv6 and unwraps IPv4-mapped addresses", () => {
    expect(clientIpFrom("2001:db8::1", 1)).toBe("2001:db8::1");
    expect(clientIpFrom("::ffff:198.51.100.4", 1)).toBe("198.51.100.4");
  });
});
