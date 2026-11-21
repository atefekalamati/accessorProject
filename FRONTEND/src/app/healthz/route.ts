export const dynamic = "force-dynamic";

/** Liveness for the container; does not call the API. */
export function GET(): Response {
  return Response.json({ status: "ok" }, { headers: { "cache-control": "no-store" } });
}
