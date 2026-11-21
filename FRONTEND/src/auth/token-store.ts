/**
 * The access token, in memory only (FRONTEND.md §3: never localStorage). Lost on reload;
 * the refresh cookie brings it back.
 */

export interface Session {
  token: string;
  /** Epoch milliseconds. */
  expiresAt: number;
}

type Listener = () => void;

let session: Session | null = null;
/** False until the first session check of this page load settled (see bootstrapSession). */
let ready = false;
const listeners = new Set<Listener>();

export function getSession(): Session | null {
  return session;
}

export function setSession(next: Session | null): void {
  if (next === session) return;
  session = next;
  notify();
}

export function isReady(): boolean {
  return ready;
}

export function setReady(next: boolean): void {
  if (next === ready) return;
  ready = next;
  notify();
}

function notify(): void {
  for (const listener of listeners) listener();
}

export function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** True when the token is valid for at least `marginMs` more. */
export function isFresh(current: Session | null, marginMs: number, now = Date.now()): boolean {
  return current !== null && current.expiresAt - now > marginMs;
}
