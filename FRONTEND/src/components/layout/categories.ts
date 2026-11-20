import "server-only";

import { unstable_rethrow } from "next/navigation";

import { SERVER_FETCH_TIMEOUT_MS, serverApi } from "@/api/server";

export interface NavCategory {
  title: string;
  slug: string;
}

/**
 * Top-level categories for the header and footer. A failure must not take the page down:
 * the navigation is then empty and the rest of the page still renders.
 */
export async function loadNavCategories(): Promise<NavCategory[]> {
  try {
    const api = await serverApi();
    const { data } = await api.GET("/api/v1/categories", {
      signal: AbortSignal.timeout(SERVER_FETCH_TIMEOUT_MS),
    });
    return (data?.items ?? []).map(({ title, slug }) => ({ title, slug }));
  } catch (error) {
    // Next.js signals (dynamic rendering, redirects) travel as errors; let them through.
    unstable_rethrow(error);
    console.error("navigation: categories unavailable", error);
    return [];
  }
}
