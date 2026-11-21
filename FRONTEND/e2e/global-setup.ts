import { startMockApi } from "./mock-api/server";

/** Starts the mock API before the tests; the returned function stops it afterwards. */
export default async function globalSetup() {
  const server = await startMockApi();
  return () => new Promise<void>((resolve) => server.close(() => resolve()));
}
