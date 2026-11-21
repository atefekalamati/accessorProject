/**
 * Idempotency-Key per user intent (FRONTEND.md §6): the same key for every attempt with the
 * same body (retries after a network error or timeout), a new key once the body changes or
 * after `renew()` (e.g. after 409 PRICE_CHANGED, or once the intent succeeded).
 */
export class IntentKey {
  private key: string | null = null;
  private body: string | null = null;

  constructor(private readonly newKey: () => string = () => crypto.randomUUID()) {}

  /** The key for this body: kept while the body is unchanged, new when it changes. */
  for(body: unknown): string {
    const serialized = stableStringify(body);
    if (this.key === null || serialized !== this.body) {
      this.key = this.newKey();
      this.body = serialized;
    }
    return this.key;
  }

  /** Start a new intent: the next `for()` returns a new key even for the same body. */
  renew(): void {
    this.key = null;
    this.body = null;
  }
}

/** JSON with object keys sorted, so equal bodies serialize equally. */
export function stableStringify(value: unknown): string {
  return JSON.stringify(value, (_key, inner: unknown) => {
    if (inner === null || typeof inner !== "object" || Array.isArray(inner)) return inner;
    return Object.fromEntries(
      Object.entries(inner as Record<string, unknown>).sort(([a], [b]) => (a < b ? -1 : 1)),
    );
  });
}
