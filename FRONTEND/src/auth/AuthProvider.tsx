"use client";

import { createContext, useContext, useEffect, useSyncExternalStore } from "react";

import { bootstrapSession, connectTabs, endSession, sameOrigin } from "./refresh";
import { getSession, isReady, subscribe } from "./token-store";

/** "unknown" until the first session check settles; data that depends on auth waits. */
export type AuthStatus = "unknown" | "authenticated" | "guest";

const AuthStatusContext = createContext<AuthStatus>("unknown");

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const session = useSyncExternalStore(subscribe, getSession, () => null);
  const ready = useSyncExternalStore(subscribe, isReady, () => false);

  useEffect(() => {
    const disconnect = connectTabs();
    void bootstrapSession();
    return disconnect;
  }, []);

  const status: AuthStatus = !ready ? "unknown" : session !== null ? "authenticated" : "guest";
  return <AuthStatusContext.Provider value={status}>{children}</AuthStatusContext.Provider>;
}

export function useAuthStatus(): AuthStatus {
  return useContext(AuthStatusContext);
}

/** Ends the session on the server and in every tab. */
export async function logout(): Promise<void> {
  try {
    await fetch(sameOrigin("/api/v1/auth/logout"), { method: "POST", credentials: "same-origin" });
  } finally {
    endSession();
  }
}
