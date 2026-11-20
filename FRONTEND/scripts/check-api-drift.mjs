// Fails when src/api/schema.gen.ts no longer matches the frozen contract
// (../BACKEND/docs/api/versions/openapi-phase-5.json). Fix: `npm run gen:api` and commit.
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const spec = join(root, "..", "BACKEND", "docs", "api", "versions", "openapi-phase-5.json");
const committed = join(root, "src", "api", "schema.gen.ts");
const dir = mkdtempSync(join(tmpdir(), "api-drift-"));
const fresh = join(dir, "schema.gen.ts");

try {
  const bin = join(root, "node_modules", "openapi-typescript", "bin", "cli.js");
  execFileSync(process.execPath, [bin, spec, "-o", fresh], { stdio: "pipe" });
  const normalize = (text) => text.replace(/\r\n/g, "\n");
  if (normalize(readFileSync(fresh, "utf8")) !== normalize(readFileSync(committed, "utf8"))) {
    console.error("src/api/schema.gen.ts is out of date with openapi-phase-5.json.");
    console.error("Run `npm run gen:api` and commit the result.");
    process.exit(1);
  }
  console.log("API types match openapi-phase-5.json.");
} finally {
  rmSync(dir, { recursive: true, force: true });
}
