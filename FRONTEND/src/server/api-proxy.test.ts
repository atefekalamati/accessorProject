import { describe, expect, it, vi } from "vitest";

import { MAX_BODY_BYTES, isSafeApiPath, proxyToApi } from "./api-proxy";

const ORIGIN = "http://api.internal:8000";

function upstream(response: Response) {
  return vi.fn<typeof fetch>(async () => response);
}

function sentRequest(fetchImpl: ReturnType<typeof upstream>) {
  const [url, init] = fetchImpl.mock.calls[0]!;
  return { url: String(url), init: init!, headers: new Headers(init!.headers) };
}

describe("proxyToApi", () => {
  it("forwards path and query to API_ORIGIN, with allowlisted headers only", async () => {
    const fetchImpl = upstream(Response.json({ ok: true }));
    const request = new Request("http://shop.test/api/v1/cart?x=1", {
      headers: {
        authorization: "Bearer abc",
        cookie: "cart_token=t",
        "idempotency-key": "k-1",
        "x-forwarded-for": "198.51.100.4",
        host: "shop.test",
        "x-custom": "dropped",
      },
    });

    await proxyToApi(request, { origin: ORIGIN, hops: 0, fetchImpl });

    const sent = sentRequest(fetchImpl);
    expect(sent.url).toBe(`${ORIGIN}/api/v1/cart?x=1`);
    expect(sent.headers.get("authorization")).toBe("Bearer abc");
    expect(sent.headers.get("cookie")).toBe("cart_token=t");
    expect(sent.headers.get("idempotency-key")).toBe("k-1");
    expect(sent.headers.get("x-custom")).toBeNull();
    expect(sent.headers.get("host")).toBeNull();
    expect(sent.init.redirect).toBe("manual");
  });

  it("replaces X-Forwarded-For / X-Real-IP with the one resolved client IP", async () => {
    const fetchImpl = upstream(new Response(null, { status: 204 }));
    const request = new Request("http://shop.test/api/v1/auth/request-otp", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-forwarded-for": "6.6.6.6, 198.51.100.4",
        "x-real-ip": "6.6.6.6",
      },
      body: JSON.stringify({ mobile: "09120000000" }),
    });

    await proxyToApi(request, { origin: ORIGIN, hops: 1, fetchImpl });

    const sent = sentRequest(fetchImpl);
    expect(sent.headers.get("x-forwarded-for")).toBe("198.51.100.4");
    expect(sent.headers.get("x-real-ip")).toBe("198.51.100.4");
    expect(new TextDecoder().decode(sent.init.body as Uint8Array)).toBe('{"mobile":"09120000000"}');
  });

  it("forwards no client IP with 0 trusted hops, whatever the client sent", async () => {
    const fetchImpl = upstream(Response.json({}));
    const request = new Request("http://shop.test/api/v1/cart", {
      headers: { "x-forwarded-for": "6.6.6.6", "x-real-ip": "6.6.6.6" },
    });

    await proxyToApi(request, { origin: ORIGIN, hops: 0, fetchImpl });

    const sent = sentRequest(fetchImpl);
    expect(sent.headers.get("x-forwarded-for")).toBeNull();
    expect(sent.headers.get("x-real-ip")).toBeNull();
  });

  it("drops client IP headers entirely when no IP can be resolved", async () => {
    const fetchImpl = upstream(Response.json({}));
    const request = new Request("http://shop.test/api/v1/cart", {
      headers: { "x-real-ip": "6.6.6.6" },
    });

    await proxyToApi(request, { origin: ORIGIN, hops: 1, fetchImpl });

    const sent = sentRequest(fetchImpl);
    expect(sent.headers.get("x-forwarded-for")).toBeNull();
    expect(sent.headers.get("x-real-ip")).toBeNull();
  });

  it("passes every Set-Cookie back separately, with status and body", async () => {
    const headers = new Headers({ "content-type": "application/json", "x-request-id": "r-1" });
    headers.append("set-cookie", "refresh_token=a; HttpOnly; Secure; Path=/api/v1/auth");
    headers.append("set-cookie", "cart_token=; Max-Age=0; Path=/api/v1");
    const fetchImpl = upstream(new Response('{"access_token":"t"}', { status: 200, headers }));

    const response = await proxyToApi(
      new Request("http://shop.test/api/v1/auth/verify-otp", { method: "POST", body: "{}" }),
      { origin: ORIGIN, hops: 0, fetchImpl },
    );

    expect(response.status).toBe(200);
    expect(response.headers.getSetCookie()).toEqual([
      "refresh_token=a; HttpOnly; Secure; Path=/api/v1/auth",
      "cart_token=; Max-Age=0; Path=/api/v1",
    ]);
    expect(response.headers.get("x-request-id")).toBe("r-1");
    expect(await response.text()).toBe('{"access_token":"t"}');
  });

  it("passes error responses through unchanged", async () => {
    const fetchImpl = upstream(
      Response.json(
        { error: { code: "OTP_RATE_LIMITED", message: "", details: [] }, request_id: "r" },
        { status: 429, headers: { "retry-after": "42" } },
      ),
    );

    const response = await proxyToApi(new Request("http://shop.test/api/v1/cart"), {
      origin: ORIGIN,
      hops: 0,
      fetchImpl,
    });

    expect(response.status).toBe(429);
    expect(response.headers.get("retry-after")).toBe("42");
  });

  it("answers 502 in the API error shape when the API is unreachable", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () => {
      throw new TypeError("fetch failed");
    });

    const response = await proxyToApi(new Request("http://shop.test/api/v1/cart"), {
      origin: ORIGIN,
      hops: 0,
      fetchImpl,
    });

    expect(response.status).toBe(502);
    const body = (await response.json()) as { error: { code: string }; request_id: string };
    expect(body.error.code).toBe("UPSTREAM_UNAVAILABLE");
    expect(body.request_id).toBeTruthy();
  });

  it("rewrites API redirects to relative paths so the internal origin is not exposed", async () => {
    const fetchImpl = upstream(
      new Response(null, { status: 307, headers: { location: `${ORIGIN}/api/v1/cart?x=1` } }),
    );

    const response = await proxyToApi(new Request("http://shop.test/api/v1/cart/"), {
      origin: ORIGIN,
      hops: 0,
      fetchImpl,
    });

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe("/api/v1/cart?x=1");
  });

  it("keeps redirects to other origins unchanged (e.g. a payment gateway)", async () => {
    const fetchImpl = upstream(
      new Response(null, { status: 302, headers: { location: "https://gateway.test/pay/1" } }),
    );

    const response = await proxyToApi(new Request("http://shop.test/api/v1/x"), {
      origin: ORIGIN,
      hops: 0,
      fetchImpl,
    });

    expect(response.headers.get("location")).toBe("https://gateway.test/pay/1");
  });

  it("answers 504 in the API error shape when the API times out", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () => {
      throw new DOMException("The operation timed out.", "TimeoutError");
    });

    const response = await proxyToApi(new Request("http://shop.test/api/v1/cart"), {
      origin: ORIGIN,
      hops: 0,
      fetchImpl,
    });

    expect(response.status).toBe(504);
    expect(((await response.json()) as { error: { code: string } }).error.code).toBe(
      "UPSTREAM_TIMEOUT",
    );
  });

  it("refuses bodies over the API limit without calling it", async () => {
    const fetchImpl = upstream(Response.json({}));
    const request = new Request("http://shop.test/api/v1/contact", {
      method: "POST",
      body: new Uint8Array(MAX_BODY_BYTES + 1),
    });

    const response = await proxyToApi(request, { origin: ORIGIN, hops: 0, fetchImpl });

    expect(response.status).toBe(413);
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("refuses paths outside /api/v1 or with traversal", async () => {
    const fetchImpl = upstream(Response.json({}));
    const response = await proxyToApi(new Request("http://shop.test/api/v1/%2e%2e/metrics"), {
      origin: ORIGIN,
      hops: 0,
      fetchImpl,
    });

    expect(response.status).toBe(404);
    expect(fetchImpl).not.toHaveBeenCalled();
  });
});

describe("isSafeApiPath", () => {
  it.each([
    ["/api/v1/cart", true],
    ["/api/v1/orders/ORD-2026-000001", true],
    ["/api/v2/cart", false],
    ["/metrics", false],
    ["/api/v1/../metrics", false],
    ["/api/v1/%2E%2E/metrics", false],
    ["/api/v1/a%2Fb", false],
    ["/api/v1/a\\b", false],
  ])("%s → %s", (path, expected) => {
    expect(isSafeApiPath(path)).toBe(expected);
  });
});
