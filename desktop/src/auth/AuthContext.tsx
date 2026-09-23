import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { authApi } from "../api/auth";
import type { OrganizationMembership, TokenPair, User } from "../api/types";
import { clearRefreshToken, getRefreshToken, setRefreshToken } from "./secureStore";
import { clearSession, configureSessionRefresh, setAccessToken, setOrganizationId } from "./authSession";

const LAST_ORGANIZATION_KEY = "vero.lastOrganizationId";

type Status = "loading" | "signedOut" | "signedIn";

interface AuthContextValue {
  status: Status;
  user: User | null;
  organizations: OrganizationMembership[];
  /** The organization every request is scoped to. */
  currentOrganizationId: string | null;
  currentRole: "owner" | "admin" | "member" | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name: string, organizationName: string) => Promise<void>;
  logout: () => Promise<void>;
  /** Rotates the token pair server-side and revokes every other session, so this call
   * both changes the password and re-authenticates the current one. */
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>;
  switchOrganization: (organizationId: string) => void;
  /** Re-fetches the current user's organizations — call after creating one, being added to
   * one, or leaving one, so the switcher reflects it without a full sign-out/in. */
  refreshOrganizations: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function rememberOrganization(id: string): void {
  try {
    window.localStorage.setItem(LAST_ORGANIZATION_KEY, id);
  } catch {
    // Not persisted across restarts — the user just lands on their first organization.
  }
}

function readRememberedOrganization(): string | null {
  try {
    return window.localStorage.getItem(LAST_ORGANIZATION_KEY);
  } catch {
    return null;
  }
}

function pickOrganizationId(organizations: OrganizationMembership[]): string | null {
  const remembered = readRememberedOrganization();
  if (remembered && organizations.some((m) => m.organization.id === remembered)) return remembered;
  return organizations[0]?.organization.id ?? null;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<Status>("loading");
  const [user, setUser] = useState<User | null>(null);
  const [organizations, setOrganizations] = useState<OrganizationMembership[]>([]);
  const [currentOrganizationId, setCurrentOrganizationId] = useState<string | null>(null);

  // Read inside the refresh handler, which authSession calls well after this render.
  const currentOrganizationIdRef = useRef<string | null>(null);
  currentOrganizationIdRef.current = currentOrganizationId;

  // Every cached query (cameras, events, analytics, locations, members...) is scoped to
  // whichever organization is currently selected. Anything cached under a different
  // organization is not just stale, it's another tenant's data, so it must not linger
  // in view for even a render.
  function applySession(tokens: TokenPair, opts: { isNewIdentity: boolean }) {
    setAccessToken(tokens.access_token);
    const orgId = pickOrganizationId(tokens.organizations) ?? currentOrganizationIdRef.current;
    if (opts.isNewIdentity || orgId !== currentOrganizationIdRef.current) {
      queryClient.clear();
    }
    setOrganizationId(orgId);
    if (orgId) rememberOrganization(orgId);
    setUser(tokens.user);
    setOrganizations(tokens.organizations);
    setCurrentOrganizationId(orgId);
    setStatus("signedIn");
  }

  const signOutLocally = useCallback(() => {
    clearSession();
    queryClient.clear();
    setUser(null);
    setOrganizations([]);
    setCurrentOrganizationId(null);
    setStatus("signedOut");
  }, [queryClient]);

  useEffect(() => {
    // Shares one implementation with the mount-time restore below: both renew the session
    // from whatever refresh token is currently in the secure store.
    async function doRefresh(): Promise<string | null> {
      const stored = await getRefreshToken();
      if (!stored) return null;
      try {
        const tokens = await authApi.refresh(stored);
        await setRefreshToken(tokens.refresh_token); // rotated — the old one no longer works
        // A silent background refresh keeps the same identity/organization almost always;
        // applySession only clears the cache if it turns out the organization actually changed.
        applySession(tokens, { isNewIdentity: false });
        return tokens.access_token;
      } catch {
        await clearRefreshToken().catch(() => {});
        return null;
      }
    }

    configureSessionRefresh({ refresh: doRefresh, onExpired: signOutLocally });

    let cancelled = false;
    (async () => {
      const renewed = await doRefresh();
      if (!cancelled && renewed === null) setStatus("signedOut");
    })();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs once; applySession/signOutLocally close over fresh setters via React's stable dispatch identity.
  }, [signOutLocally]);

  const login = useCallback(async (email: string, password: string) => {
    const tokens = await authApi.login({ email, password });
    await setRefreshToken(tokens.refresh_token);
    applySession(tokens, { isNewIdentity: true });
  }, []);

  const register = useCallback(
    async (email: string, password: string, name: string, organizationName: string) => {
      const tokens = await authApi.register({ email, password, name, organization_name: organizationName });
      await setRefreshToken(tokens.refresh_token);
      applySession(tokens, { isNewIdentity: true });
    },
    [],
  );

  const changePassword = useCallback(async (currentPassword: string, newPassword: string) => {
    const tokens = await authApi.changePassword({ current_password: currentPassword, new_password: newPassword });
    await setRefreshToken(tokens.refresh_token);
    applySession(tokens, { isNewIdentity: false });
  }, []);

  const logout = useCallback(async () => {
    const stored = await getRefreshToken();
    if (stored) {
      // Best-effort: the local session is cleared either way, even if the backend is
      // unreachable right now.
      await authApi.logout(stored).catch(() => {});
    }
    await clearRefreshToken().catch(() => {});
    signOutLocally();
  }, [signOutLocally]);

  const switchOrganization = useCallback(
    (organizationId: string) => {
      if (organizationId !== currentOrganizationIdRef.current) {
        queryClient.clear();
      }
      setOrganizationId(organizationId);
      setCurrentOrganizationId(organizationId);
      rememberOrganization(organizationId);
    },
    [queryClient],
  );

  const refreshOrganizations = useCallback(async () => {
    const me = await authApi.me();
    setUser(me.user);
    setOrganizations(me.organizations);
    // Keep the current selection if it's still valid; otherwise fall back sensibly.
    setCurrentOrganizationId((current) => {
      const stillMember = current && me.organizations.some((m) => m.organization.id === current);
      const next = stillMember ? current : pickOrganizationId(me.organizations);
      if (next !== current) queryClient.clear();
      setOrganizationId(next);
      if (next) rememberOrganization(next);
      return next;
    });
  }, [queryClient]);

  const currentRole = useMemo(
    () => organizations.find((m) => m.organization.id === currentOrganizationId)?.role ?? null,
    [organizations, currentOrganizationId],
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      organizations,
      currentOrganizationId,
      currentRole,
      login,
      register,
      logout,
      changePassword,
      switchOrganization,
      refreshOrganizations,
    }),
    [
      status,
      user,
      organizations,
      currentOrganizationId,
      currentRole,
      login,
      register,
      logout,
      changePassword,
      switchOrganization,
      refreshOrganizations,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}

// Exported so tests can render `<AuthContext.Provider value={...}>` directly around just the
// component under test — see src/test/authFixtures.ts — instead of mounting the real
// AuthProvider (whose effects touch the secure store and the network).
export { AuthContext };
export type { AuthContextValue };
