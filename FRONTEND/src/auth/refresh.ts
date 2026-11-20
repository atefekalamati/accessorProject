import { clearSessionHint, hasSessionHint, setSessionHint } from "./session-hint";
import { getSession, isFresh, setReady, setSession, subscribe, type Session } from "./token-store";

/**
 * Single-flight token refresh (FRONTEND.md §3, ADR-017/018).
 *
 * The API rotates the refresh token on every refresh and treats two refreshes with the same
 * cookie as reuse, which ends the whole session. So:
 * - in a tab, every caller shares one promise;
 * - across tabs, the refresh runs inside a Web Lock, and a tab that gets the lock first
 *   checks whether another tab already got a fresh token (shared via BroadcastChannel);
 * - a 401 from refresh ends the session: state is cleared and it is never retried.
 */

export const REFRESH_PATH = "/api/v1/auth/refresh";
export const LOCK_NAME = "ak-auth-refresh";
export const CHANNEL_NAME = "ak-auth";
/** Refresh this long before expiry, and treat a token closer to expiry as stale. */
export const REFRESH_MARGIN_MS = 60_000;

type ChannelMessage = { type: "session"; session: Session } | { type: "logout" };

/** A refresh that failed for a reason other than "session over" (network, 429, 5xx). */
export class RefreshUnavailableError extends Error {
  constructor(readonly status: number | null) {
    super(status === null ? "Refresh failed: network" : `Refresh failed: HTTP ${status}`);
    this.name = "RefreshUnavailableError";
  }
}

let inflight: Promise<string | null> | null = null;
let bootstrapped: Promise<void> | null = null;
let channel: BroadcastChannel | null = null;
let timer: ReturnType<typeof setTimeout> | null = null;

/**
 * The first session check of a page load: the access token is gone after a reload, so
 * refresh once when the hint says a refresh cookie probably exists. Marks the store ready
 * whatever the outcome (a transient failure leaves the visitor a guest for now).
 */
export function bootstrapSession(): Promise<void> {
  if (bootstrapped === null) {
    bootstrapped = (async () => {
      if (getSession() !== null || !hasSessionHint()) return;
      try {
        await refreshAccessToken();
      } catch {
        // Network or server trouble; the hint stays for the next attempt.
      }
    })().finally(() => setReady(true));
  }
  return bootstrapped;
}

/**
 * A fresh access token, or null when the session is over. Concurrent calls share one
 * request. Throws RefreshUnavailableError on transient failures.
 *
 * `staleToken` is the token the caller found wanting (e.g. the one that got a 401). When the
 * current token is already a different, fresh one, it is returned without a refresh: a
 * rotation elsewhere revoked the old token, and refreshing again would revoke the new one
 * for every request in flight.
 */
export function refreshAccessToken(staleToken?: string | null): Promise<string | null> {
  const stale = staleToken === undefined ? (getSession()?.token ?? null) : staleToken;
  const current = getSession();
  if (current !== null && current.token !== stale && isFresh(current, REFRESH_MARGIN_MS)) {
    return Promise.resolve(current.token);
  }
  if (inflight === null) {
    inflight = withCrossTabLock((contended) => refreshUnlessDone(stale, contended)).finally(() => {
      inflight = null;
    });
  }
  return inflight;
}

/** Store a session from verify-otp or refresh, and tell the other tabs. */
export function startSession(token: string, expiresInSeconds: number): void {
  const session = { token, expiresAt: Date.now() + expiresInSeconds * 1000 };
  applySession(session);
  setSessionHint();
  post({ type: "session", session });
}

/** Clear the session here and in the other tabs (logout or a refresh 401). */
export function endSession(): void {
  applySession(null);
  clearSessionHint();
  post({ type: "logout" });
}

/** Listen to the other tabs. Call once in the browser; returns a cleanup function. */
export function connectTabs(): () => void {
  const current = openChannel();
  if (current === null) return () => {};
  const onMessage = (event: MessageEvent<ChannelMessage>) => {
    const message = event.data;
    if (message.type === "session") applySession(message.session);
    else if (message.type === "logout") applySession(null);
  };
  current.addEventListener("message", onMessage);
  return () => current.removeEventListener("message", onMessage);
}

/** How long a tab that waited for the lock waits for the holder's broadcast token. */
export const CHANNEL_GRACE_MS = 250;

async function refreshUnlessDone(
  staleToken: string | null,
  contended: boolean,
): Promise<string | null> {
  // Another tab may have refreshed while we waited for the lock; its token reaches us over
  // the channel. Lock release and channel delivery are separate task sources, so after
  // waiting for the lock give the message a moment before refreshing ourselves.
  if (contended) await sessionChangeOrTimeout(staleToken, CHANNEL_GRACE_MS);
  const current = getSession();
  if (current !== null && current.token !== staleToken && isFresh(current, REFRESH_MARGIN_MS)) {
    return current.token;
  }

  let response: Response;
  try {
    response = await fetch(sameOrigin(REFRESH_PATH), {
      method: "POST",
      credentials: "same-origin",
    });
  } catch {
    throw new RefreshUnavailableError(null);
  }

  if (response.status === 401) {
    endSession();
    return null;
  }
  if (!response.ok) throw new RefreshUnavailableError(response.status);

  let body: { access_token?: unknown; expires_in_seconds?: unknown };
  try {
    body = (await response.json()) as typeof body;
  } catch {
    throw new RefreshUnavailableError(response.status);
  }
  if (typeof body.access_token !== "string" || typeof body.expires_in_seconds !== "number") {
    throw new RefreshUnavailableError(response.status);
  }
  startSession(body.access_token, body.expires_in_seconds);
  return body.access_token;
}

/** Resolves when the session token differs from `token`, or after `ms`. */
function sessionChangeOrTimeout(token: string | null, ms: number): Promise<void> {
  if ((getSession()?.token ?? null) !== token) return Promise.resolve();
  return new Promise((resolve) => {
    const done = () => {
      clearTimeout(timeout);
      unsubscribe();
      resolve();
    };
    const timeout = setTimeout(done, ms);
    const unsubscribe = subscribe(() => {
      if ((getSession()?.token ?? null) !== token) done();
    });
  });
}

/** An absolute same-origin URL (Request needs one outside the browser, e.g. in tests). */
export function sameOrigin(path: string): string {
  return new URL(path, window.location.origin).toString();
}

/**
 * Runs `task` holding the cross-tab lock; `contended` tells it whether it had to wait.
 * Without Web Locks (very old browsers) only the in-tab single-flight applies.
 */
async function withCrossTabLock<T>(task: (contended: boolean) => Promise<T>): Promise<T> {
  const locks = typeof navigator !== "undefined" ? navigator.locks : undefined;
  if (locks === undefined) return task(false);
  const busy = Symbol("busy");
  const first = (await locks.request(LOCK_NAME, { mode: "exclusive", ifAvailable: true }, (lock) =>
    lock === null ? busy : task(false),
  )) as T | typeof busy;
  if (first !== busy) return first;
  return locks.request(LOCK_NAME, { mode: "exclusive" }, () => task(true)) as Promise<T>;
}

function applySession(session: Session | null): void {
  setSession(session);
  scheduleProactiveRefresh(session);
}

function scheduleProactiveRefresh(session: Session | null): void {
  if (timer !== null) clearTimeout(timer);
  timer = null;
  if (session === null || typeof window === "undefined") return;
  const delay = Math.max(session.expiresAt - Date.now() - REFRESH_MARGIN_MS, 0);
  timer = setTimeout(() => {
    refreshAccessToken().catch(() => {
      // Transient; the next API call that gets a 401 tries again.
    });
  }, delay);
}

function openChannel(): BroadcastChannel | null {
  if (channel === null && typeof BroadcastChannel !== "undefined") {
    channel = new BroadcastChannel(CHANNEL_NAME);
  }
  return channel;
}

function post(message: ChannelMessage): void {
  openChannel()?.postMessage(message);
}

/** Test-only: forget module state between tests. */
export function resetRefreshStateForTests(): void {
  inflight = null;
  bootstrapped = null;
  setReady(false);
  if (timer !== null) clearTimeout(timer);
  timer = null;
  channel?.close();
  channel = null;
  setSession(null);
}
