import { expect, test } from "@playwright/test";

const MOCK_API = "http://127.0.0.1:8787";

test.describe("same-origin API proxy", () => {
  test.skip(({ isMobile }) => isMobile, "server behaviour; one viewport is enough");

  test("forwards /api/v1/* to API_ORIGIN and returns the API's JSON", async ({ request }) => {
    const response = await request.get("/api/v1/categories");
    expect(response.status()).toBe(200);
    const body = (await response.json()) as { items: { slug: string }[] };
    expect(body.items.map((item) => item.slug)).toContain("bags");
  });

  test("replaces a forged X-Forwarded-For with the trusted hop's client IP", async ({
    request,
  }) => {
    const requestId = crypto.randomUUID();
    await request.get("/api/v1/cart", {
      headers: {
        "x-request-id": requestId,
        "x-forwarded-for": "6.6.6.6, 198.51.100.9",
        "x-real-ip": "6.6.6.6",
      },
    });

    const recordedResponse = await request.get(`${MOCK_API}/__mock/requests/${requestId}`);
    expect(recordedResponse.status()).toBe(200);
    const recorded = (await recordedResponse.json()) as {
      path: string;
      headers: Record<string, string>;
    };
    expect(recorded.path).toBe("/api/v1/cart");
    expect(recorded.headers["x-forwarded-for"]).toBe("198.51.100.9");
    expect(recorded.headers["x-real-ip"]).toBe("198.51.100.9");
  });

  test("answers unknown API paths with the API's 404 error shape", async ({ request }) => {
    const response = await request.get("/api/v1/does-not-exist");
    expect(response.status()).toBe(404);
    expect(((await response.json()) as { error: { code: string } }).error.code).toBe("NOT_FOUND");
  });
});
