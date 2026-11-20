import { HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { errorBody, tokenResponse } from "../../test/msw/fixtures";
import { http } from "../../test/msw/handlers";
import { server } from "../../test/msw/server";

import {
  RefreshUnavailableError,
  bootstrapSession,
  endSession,
  refreshAccessToken,
  resetRefreshStateForTests,
  startSession,
} from "./refresh";
import { hasSessionHint, setSessionHint } from "./session-hint";
import { getSession, isReady, setSession } from "./token-store";

function countRefreshes(respond: () => Response) {
  let calls = 0;
  server.use(
    http.post("/api/v1/auth/refresh", () => {
      calls += 1;
      return respond();
    }),
  );
  return () => calls;
}

afterEach(() => resetRefreshStateForTests());

describe("refreshAccessToken", () => {
  it("shares one request between concurrent callers (single-flight)", async () => {
    const calls = countRefreshes(() => HttpResponse.json(tokenResponse));

    const tokens = await Promise.all(Array.from({ length: 5 }, () => refreshAccessToken()));

    expect(calls()).toBe(1);
    expect(new Set(tokens)).toEqual(new Set(["test-access-token"]));
    expect(getSession()?.token).toBe("test-access-token");
    expect(hasSessionHint()).toBe(true);
  });

  it("starts a new request once the previous one settled", async () => {
    const calls = countRefreshes(() => HttpResponse.json(tokenResponse));

    await refreshAccessToken();
    setSession({ token: "test-access-token", expiresAt: Date.now() + 1000 });
    await refreshAccessToken();

    expect(calls()).toBe(2);
  });

  it("ends the session on 401 and does not retry", async () => {
    const calls = countRefreshes(() =>
      HttpResponse.json(errorBody("UNAUTHORIZED"), { status: 401 }),
    );
    startSession("old", 900);
    setSessionHint();

    await expect(refreshAccessToken()).resolves.toBeNull();

    expect(calls()).toBe(1);
    expect(getSession()).toBeNull();
    expect(hasSessionHint()).toBe(false);
  });

  it("keeps the session on transient failures and reports them", async () => {
    countRefreshes(() => HttpResponse.json(errorBody("SERVICE_UNAVAILABLE"), { status: 503 }));
    startSession("current", 30);

    await expect(refreshAccessToken()).rejects.toBeInstanceOf(RefreshUnavailableError);
    expect(getSession()?.token).toBe("current");
  });

  /** A Web Lock held by another tab until `release()`; honours `ifAvailable`. */
  function stubLockHeldByOtherTab() {
    let release!: () => void;
    const held = new Promise<void>((resolve) => (release = resolve));
    const requests: { name: string; ifAvailable: boolean }[] = [];
    vi.stubGlobal("navigator", {
      ...navigator,
      locks: {
        request: async (
          name: string,
          options: { ifAvailable?: boolean },
          task: (lock: object | null) => Promise<unknown>,
        ) => {
          requests.push({ name, ifAvailable: options.ifAvailable === true });
          if (options.ifAvailable) return task(null);
          await held;
          return task({ name });
        },
      },
    });
    return { release, requests };
  }

  it("uses a fresh token another tab already obtained instead of refreshing again", async () => {
    const calls = countRefreshes(() => HttpResponse.json(tokenResponse));
    const lock = stubLockHeldByOtherTab();
    setSession({ token: "stale", expiresAt: Date.now() + 10_000 });

    const pending = refreshAccessToken();
    // The other tab refreshed; its token reached this tab over BroadcastChannel.
    setSession({ token: "from-other-tab", expiresAt: Date.now() + 900_000 });
    lock.release();

    await expect(pending).resolves.toBe("from-other-tab");
    expect(calls()).toBe(0);
    expect(lock.requests.map((request) => request.name)).toEqual([
      "ak-auth-refresh",
      "ak-auth-refresh",
    ]);
    vi.unstubAllGlobals();
  });

  it("after waiting for the lock, waits briefly for the other tab's broadcast", async () => {
    const calls = countRefreshes(() => HttpResponse.json(tokenResponse));
    const lock = stubLockHeldByOtherTab();
    setSession({ token: "stale", expiresAt: Date.now() + 10_000 });

    const pending = refreshAccessToken();
    // The lock is released before the channel message arrives (different task sources).
    lock.release();
    await new Promise((resolve) => setTimeout(resolve, 20));
    setSession({ token: "from-other-tab", expiresAt: Date.now() + 900_000 });

    await expect(pending).resolves.toBe("from-other-tab");
    expect(calls()).toBe(0);
    vi.unstubAllGlobals();
  });

  it("returns the current token without refreshing when the rejected one was already replaced", async () => {
    const calls = countRefreshes(() => HttpResponse.json(tokenResponse));
    setSession({ token: "rotated", expiresAt: Date.now() + 900_000 });

    await expect(refreshAccessToken("revoked")).resolves.toBe("rotated");
    expect(calls()).toBe(0);
  });

  it("reports a malformed 200 as a transient failure", async () => {
    countRefreshes(() => new HttpResponse("not json", { status: 200 }));

    await expect(refreshAccessToken()).rejects.toBeInstanceOf(RefreshUnavailableError);
  });

  it("bootstrap: a guest without the hint becomes ready without a refresh call", async () => {
    const calls = countRefreshes(() => HttpResponse.json(tokenResponse));

    await bootstrapSession();

    expect(calls()).toBe(0);
    expect(isReady()).toBe(true);
    expect(getSession()).toBeNull();
  });

  it("bootstrap: with the hint, refreshes once even if called repeatedly", async () => {
    const calls = countRefreshes(() => HttpResponse.json(tokenResponse));
    setSessionHint();

    await Promise.all([bootstrapSession(), bootstrapSession()]);

    expect(calls()).toBe(1);
    expect(isReady()).toBe(true);
    expect(getSession()?.token).toBe("test-access-token");
  });

  it("endSession clears the token and the hint", () => {
    startSession("t", 900);
    endSession();
    expect(getSession()).toBeNull();
    expect(hasSessionHint()).toBe(false);
  });
});
