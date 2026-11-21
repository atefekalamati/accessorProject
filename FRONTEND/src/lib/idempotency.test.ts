import { describe, expect, it } from "vitest";

import { IntentKey, stableStringify } from "./idempotency";

function sequentialKeys() {
  let n = 0;
  return () => `key-${++n}`;
}

describe("IntentKey", () => {
  it("keeps the key while the body is unchanged (retries reuse it)", () => {
    const intent = new IntentKey(sequentialKeys());
    const body = { address_id: "a", shipping_method_id: "s", fingerprint: "f" };

    expect(intent.for(body)).toBe("key-1");
    expect(intent.for({ ...body })).toBe("key-1");
  });

  it("ignores key order when comparing bodies", () => {
    const intent = new IntentKey(sequentialKeys());
    intent.for({ a: 1, b: 2 });
    expect(intent.for({ b: 2, a: 1 })).toBe("key-1");
  });

  it("makes a new key when the body changes (e.g. a new fingerprint after PRICE_CHANGED)", () => {
    const intent = new IntentKey(sequentialKeys());
    intent.for({ fingerprint: "old" });
    expect(intent.for({ fingerprint: "new" })).toBe("key-2");
  });

  it("makes a new key after renew() even for the same body", () => {
    const intent = new IntentKey(sequentialKeys());
    intent.for({ order_id: "o" });
    intent.renew();
    expect(intent.for({ order_id: "o" })).toBe("key-2");
  });

  it("uses random UUIDs by default", () => {
    expect(new IntentKey().for({})).toMatch(/^[0-9a-f-]{36}$/);
  });
});

describe("stableStringify", () => {
  it("sorts nested object keys and keeps array order", () => {
    expect(stableStringify({ b: { d: 1, c: 2 }, a: [3, 1] })).toBe('{"a":[3,1],"b":{"c":2,"d":1}}');
  });
});
