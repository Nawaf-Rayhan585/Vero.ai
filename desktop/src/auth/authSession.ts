/**
 * The current session's access token and chosen organization, as a plain module rather
 * than React state — `api/client.ts` reads it on every request, and hooks/components that
 * are not inside a component tree (or want to avoid a render-order dependency on
 * AuthProvider) can read it too. `auth/AuthContext.tsx` is the only thing that should call
 * the setters below; everything else should go through `useAuth()`.
 */
import type { TokenPair } from "../api/types";

let accessToken: string | null = null;
let organizationId: string | null = null;

// Set once by AuthProvider on mount. `refresh` re-authenticates using the stored refresh
// token and returns the new access token, or null if the session could not be renewed.
// `onExpired` is called when that happens, so AuthProvider can sign the user out.
let refreshFn: (() => Promise<string | null>) | null = null;
let onExpired: (() => void) | null = null;
// Concurrent 401s share one refresh attempt instead of each racing to rotate the refresh
// token — only the first would succeed, and the others would wrongly look expired.
let refreshInFlight: Promise<string | null> | null = null;

export function getAccessToken(): string | null {
  return accessToken;
}

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function getOrganizationId(): string | null {
  return organizationId;
}

export function setOrganizationId(id: string | null): void {
  organizationId = id;
}

export function applyTokenPair(tokens: Pick<TokenPair, "access_token" | "expires_in">): void {
  setAccessToken(tokens.access_token);
}

export function configureSessionRefresh(handlers: { refresh: () => Promise<string | null>; onExpired: () => void }): void {
  refreshFn = handlers.refresh;
  onExpired = handlers.onExpired;
}

/** Called by api/client.ts when a request 401s. Tries once to renew the session; if that
 * fails, signs the session out and returns null so the caller can surface the 401. */
export async function refreshAccessToken(): Promise<string | null> {
  if (!refreshFn) return null;
  if (!refreshInFlight) {
    refreshInFlight = refreshFn().finally(() => {
      refreshInFlight = null;
    });
  }
  const token = await refreshInFlight;
  if (token === null) {
    onExpired?.();
  }
  return token;
}

export function clearSession(): void {
  accessToken = null;
  organizationId = null;
}
