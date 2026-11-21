import { createOpenApiHttp } from "openapi-msw";

import type { paths } from "../../src/api/schema.gen";

import { categoryTree, emptyCart } from "./fixtures";

/**
 * Schema-typed handlers: paths, params and bodies are checked against openapi-phase-5.
 * `*` matches any origin, so the same handlers serve jsdom (same-origin /api/v1) and the
 * e2e mock API (a separate port).
 */
export const http = createOpenApiHttp<paths>({ baseUrl: "*" });

export const defaultHandlers = [
  http.get("/api/v1/categories", ({ response }) => response(200).json(categoryTree)),
  http.get("/api/v1/cart", ({ response }) => response(200).json(emptyCart)),
  http.post("/api/v1/auth/refresh", ({ response }) =>
    response(401).json({
      error: { code: "UNAUTHORIZED", message: "No session", details: [] },
      request_id: "5d1c4c1e-0000-4000-8000-000000000001",
    }),
  ),
];
