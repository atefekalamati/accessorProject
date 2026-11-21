import { QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderOptions } from "@testing-library/react";

import { makeQueryClient } from "../src/app/providers";
import { AuthProvider } from "../src/auth/AuthProvider";

/** Render with the app's providers and a fresh query client (no retries in tests). */
export function renderWithProviders(ui: React.ReactElement, options?: RenderOptions) {
  const client = makeQueryClient();
  client.setDefaultOptions({ queries: { retry: false, staleTime: 0 } });
  return render(
    <QueryClientProvider client={client}>
      <AuthProvider>{ui}</AuthProvider>
    </QueryClientProvider>,
    options,
  );
}
