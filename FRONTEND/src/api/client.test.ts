import { afterEach, describe, expect, it } from "vitest";

import { cartWith, cartLine, emptyCart, errorBody, tokenResponse } from "../../test/msw/fixtures";
import { http } from "../../test/msw/handlers";
import { server } from "../../test/msw/server";
import { resetRefreshStateForTests, startSession } from "../auth/refresh";
import { setSessionHint } from "../auth/session-hint";

import { api } from "./client";
import { ApiError, unwrap } from "./errors";

afterEach(() => resetRefreshStateForTests());

describe("api client (authFetch)", () => {
  it("sends no Authorization header for a guest", async () => {
    let authorization: string | null = "unset";
    server.use(
      http.get("/api/v1/cart", ({ request, response }) => {
        authorization = request.headers.get("authorization");
        return response(200).json(emptyCart);
      }),
    );

    await unwrap(api.GET("/api/v1/cart"));

    expect(authorization).toBeNull();
  });

  it("sends the in-memory access token as a Bearer header", async () => {
    let authorization: string | null = null;
    server.use(
      http.get("/api/v1/cart", ({ request, response }) => {
        authorization = request.headers.get("authorization");
        return response(200).json(emptyCart);
      }),
    );
    startSession("live-token", 900);

    await unwrap(api.GET("/api/v1/cart"));

    expect(authorization).toBe("Bearer live-token");
  });

  it("on 401 waits for one refresh and retries once with the new token", async () => {
    const seen: (string | null)[] = [];
    let refreshes = 0;
    server.use(
      http.get("/api/v1/cart", ({ request, response }) => {
        const header = request.headers.get("authorization");
        seen.push(header);
        return header === "Bearer test-access-token"
          ? response(200).json(cartWith([cartLine()]))
          : response(401).json(errorBody("UNAUTHORIZED"));
      }),
      http.post("/api/v1/auth/refresh", ({ response }) => {
        refreshes += 1;
        return response(200).json(tokenResponse);
      }),
    );
    startSession("revoked-token", 900);

    const [first, second] = await Promise.all([
      unwrap(api.GET("/api/v1/cart")),
      unwrap(api.GET("/api/v1/cart")),
    ]);

    expect(refreshes).toBe(1);
    expect(first.items).toHaveLength(1);
    expect(second.items).toHaveLength(1);
    expect(seen.filter((header) => header === "Bearer revoked-token")).toHaveLength(2);
  });

  it("on 401 after a rotation elsewhere, retries with the current token without refreshing", async () => {
    let refreshes = 0;
    server.use(
      http.get("/api/v1/cart", ({ request, response }) => {
        if (request.headers.get("authorization") === "Bearer t1") {
          // Meanwhile another request rotated T1 → T2 (the API revokes T1 at once).
          startSession("t2", 900);
          return response(401).json(errorBody("UNAUTHORIZED"));
        }
        return response(200).json(emptyCart);
      }),
      http.post("/api/v1/auth/refresh", ({ response }) => {
        refreshes += 1;
        return response(200).json(tokenResponse);
      }),
    );
    startSession("t1", 900);

    await unwrap(api.GET("/api/v1/cart"));

    expect(refreshes).toBe(0);
  });

  it("returns the 401 and never retries as a guest when the session ended", async () => {
    const seen: (string | null)[] = [];
    server.use(
      http.post("/api/v1/cart/items", ({ request, response }) => {
        seen.push(request.headers.get("authorization"));
        return response(401).json(errorBody("UNAUTHORIZED"));
      }),
      http.post("/api/v1/auth/refresh", ({ response }) =>
        response(401).json(errorBody("UNAUTHORIZED")),
      ),
    );
    startSession("revoked-token", 900);

    const error = await unwrap(
      api.POST("/api/v1/cart/items", {
        body: { variant_id: "6a0f3f3e-1b7d-4a55-8a3c-222222222222", quantity: 1 },
      }),
    ).catch((caught: unknown) => caught);

    expect((error as ApiError).status).toBe(401);
    expect(seen).toEqual(["Bearer revoked-token"]);
  });

  it("does not send a signed-in request as a guest when the session check fails", async () => {
    let cartCalls = 0;
    server.use(
      http.post("/api/v1/auth/refresh", ({ response }) =>
        response(503).json(errorBody("SERVICE_UNAVAILABLE")),
      ),
      http.get("/api/v1/cart", ({ response }) => {
        cartCalls += 1;
        return response(200).json(emptyCart);
      }),
    );
    setSessionHint();

    const error = await unwrap(api.GET("/api/v1/cart")).catch((caught: unknown) => caught);

    expect((error as ApiError).code).toBe("SESSION_UNAVAILABLE");
    expect(cartCalls).toBe(0);
  });

  it("refreshes before the request when only the session hint is present", async () => {
    let authorization: string | null = null;
    server.use(
      http.post("/api/v1/auth/refresh", ({ response }) => response(200).json(tokenResponse)),
      http.get("/api/v1/cart", ({ request, response }) => {
        authorization = request.headers.get("authorization");
        return response(200).json(emptyCart);
      }),
    );
    setSessionHint();

    await unwrap(api.GET("/api/v1/cart"));

    expect(authorization).toBe("Bearer test-access-token");
  });

  it("never attaches the token to auth endpoints", async () => {
    let authorization: string | null = "unset";
    server.use(
      http.post("/api/v1/auth/request-otp", ({ request, response }) => {
        authorization = request.headers.get("authorization");
        return response(200).json({ expires_in_seconds: 120, resend_after_seconds: 60 });
      }),
    );
    startSession("live-token", 900);

    await unwrap(api.POST("/api/v1/auth/request-otp", { body: { mobile: "09120000000" } }));

    expect(authorization).toBeNull();
  });

  it("turns error responses into ApiError with code, details and request id", async () => {
    server.use(
      http.get("/api/v1/cart", ({ response }) =>
        response(429).json(errorBody("RATE_LIMITED", [{ type: "too_many" }]), {
          headers: { "retry-after": "30" },
        }),
      ),
    );

    const error = await unwrap(api.GET("/api/v1/cart")).catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiError);
    const apiError = error as ApiError;
    expect(apiError.status).toBe(429);
    expect(apiError.code).toBe("RATE_LIMITED");
    expect(apiError.hasDetailType("too_many")).toBe(true);
    expect(apiError.retryAfter).toBe(30);
    expect(apiError.requestId).toBe("5d1c4c1e-0000-4000-8000-000000000000");
  });
});
