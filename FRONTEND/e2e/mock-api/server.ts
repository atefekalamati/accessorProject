import { createServer, type IncomingMessage, type Server } from "node:http";

import { getResponse } from "msw";

import { defaultHandlers } from "../../test/msw/handlers";

/**
 * Mock API for e2e: serves the schema-typed MSW handlers over HTTP, playing API_ORIGIN.
 * The real backend cannot be used in CI yet: OTP codes are only readable in its process
 * (see docs/BACKEND-FOLLOWUPS.md).
 *
 * Test-only endpoint (not part of the contract): GET /__mock/requests/<x-request-id>
 * returns the method, path and headers of the request sent with that X-Request-ID, to check
 * what the proxy forwards. Keyed by id so parallel workers do not see each other's requests.
 */

export const MOCK_API_PORT = 8787;

interface RecordedRequest {
  method: string;
  path: string;
  headers: Record<string, string>;
}

export function startMockApi(port = MOCK_API_PORT): Promise<Server> {
  const recorded = new Map<string, RecordedRequest>();

  const server = createServer(async (incoming, outgoing) => {
    const url = new URL(incoming.url ?? "/", `http://127.0.0.1:${port}`);

    if (url.pathname.startsWith("/__mock/requests/")) {
      const entry = recorded.get(
        decodeURIComponent(url.pathname.slice("/__mock/requests/".length)),
      );
      outgoing.writeHead(entry ? 200 : 404, { "content-type": "application/json" });
      outgoing.end(JSON.stringify(entry ?? null));
      return;
    }

    const headers = new Headers();
    for (const [name, value] of Object.entries(incoming.headers)) {
      if (typeof value === "string") headers.set(name, value);
      else if (Array.isArray(value)) value.forEach((item) => headers.append(name, item));
    }
    const requestId = headers.get("x-request-id");
    if (requestId !== null) {
      recorded.set(requestId, {
        method: incoming.method ?? "GET",
        path: url.pathname + url.search,
        headers: Object.fromEntries(headers.entries()),
      });
    }

    const method = incoming.method ?? "GET";
    const body =
      method === "GET" || method === "HEAD" ? undefined : Uint8Array.from(await readAll(incoming));
    const request = new Request(url, { method, headers, body });
    const response = await getResponse(defaultHandlers, request);

    if (response === undefined) {
      outgoing.writeHead(404, { "content-type": "application/json" });
      outgoing.end(
        JSON.stringify({
          error: { code: "NOT_FOUND", message: "No mock handler", details: [] },
          request_id: "00000000-0000-4000-8000-000000000000",
        }),
      );
      return;
    }

    const responseHeaders: Record<string, string | string[]> = {};
    response.headers.forEach((value, name) => {
      if (name !== "set-cookie") responseHeaders[name] = value;
    });
    const cookies = response.headers.getSetCookie();
    if (cookies.length > 0) responseHeaders["set-cookie"] = cookies;
    outgoing.writeHead(response.status, responseHeaders);
    outgoing.end(Buffer.from(await response.arrayBuffer()));
  });

  return new Promise((resolve) => server.listen(port, "127.0.0.1", () => resolve(server)));
}

function readAll(stream: IncomingMessage): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    stream.on("data", (chunk: Buffer) => chunks.push(chunk));
    stream.on("end", () => resolve(Buffer.concat(chunks)));
    stream.on("error", reject);
  });
}
