import { proxyToApi } from "@/server/api-proxy";
import { apiOrigin, trustedProxyHops } from "@/server/env";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

function handle(request: Request): Promise<Response> {
  return proxyToApi(request, { origin: apiOrigin(), hops: trustedProxyHops() });
}

export { handle as GET, handle as POST, handle as PUT, handle as PATCH, handle as DELETE };
