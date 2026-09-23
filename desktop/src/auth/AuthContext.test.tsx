import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider, useAuth, type AuthContextValue } from "./AuthContext";
import { refreshAccessToken } from "./authSession";
import { authApi } from "../api/auth";
import * as secureStore from "./secureStore";
import type { MeResponse, TokenPair } from "../api/types";

vi.mock("../api/auth");
vi.mock("./secureStore");

const authApiMock = vi.mocked(authApi);
const secureStoreMock = vi.mocked(secureStore);

const USER = { id: "u1", email: "owner@example.com", name: "Owner", created_at: "2026-01-01T00:00:00Z" };
const ORG_A = { id: "org-a", name: "Org A", created_at: "2026-01-01T00:00:00Z" };
const ORG_B = { id: "org-b", name: "Org B", created_at: "2026-01-01T00:00:00Z" };

function tokenPair(overrides: Partial<TokenPair> = {}): TokenPair {
  return {
    access_token: "access-token",
    refresh_token: "refresh-token",
    token_type: "bearer",
    expires_in: 900,
    user: USER,
    organizations: [{ organization: ORG_A, role: "owner" }],
    ...overrides,
  };
}

// Reassigned on every render by <Consumer>, so tests can both read the latest context value
// and call its methods without threading render results through every assertion.
let latest: AuthContextValue;
function Consumer() {
  latest = useAuth();
  return null;
}

function renderAuth(queryClient = new QueryClient()) {
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <Consumer />
      </AuthProvider>
    </QueryClientProvider>,
  );
}

describe("AuthProvider", () => {
  beforeEach(() => {
    window.localStorage.clear();
    secureStoreMock.getRefreshToken.mockResolvedValue(null);
    secureStoreMock.setRefreshToken.mockResolvedValue(undefined);
    secureStoreMock.clearRefreshToken.mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.resetAllMocks();
  });

  it("signs out when there is no stored refresh token", async () => {
    renderAuth();
    await waitFor(() => expect(latest.status).toBe("signedOut"));
  });

  it("restores a session on mount from a stored refresh token", async () => {
    secureStoreMock.getRefreshToken.mockResolvedValue("stored-refresh");
    authApiMock.refresh.mockResolvedValue(tokenPair());

    renderAuth();

    await waitFor(() => expect(latest.status).toBe("signedIn"));
    expect(latest.user?.email).toBe("owner@example.com");
    expect(latest.currentOrganizationId).toBe(ORG_A.id);
    expect(authApiMock.refresh).toHaveBeenCalledWith("stored-refresh");
  });

  it("clears the stored token and signs out when restoring fails", async () => {
    secureStoreMock.getRefreshToken.mockResolvedValue("stale-refresh");
    authApiMock.refresh.mockRejectedValue(new Error("expired"));

    renderAuth();

    await waitFor(() => expect(latest.status).toBe("signedOut"));
    expect(secureStoreMock.clearRefreshToken).toHaveBeenCalled();
  });

  it("login stores the refresh token and signs in", async () => {
    authApiMock.login.mockResolvedValue(tokenPair());
    renderAuth();
    await waitFor(() => expect(latest.status).toBe("signedOut"));

    await act(async () => {
      await latest.login("owner@example.com", "password123");
    });

    expect(secureStoreMock.setRefreshToken).toHaveBeenCalledWith("refresh-token");
    expect(latest.status).toBe("signedIn");
    expect(latest.currentOrganizationId).toBe(ORG_A.id);
  });

  it("register stores the refresh token and signs in", async () => {
    authApiMock.register.mockResolvedValue(tokenPair());
    renderAuth();
    await waitFor(() => expect(latest.status).toBe("signedOut"));

    await act(async () => {
      await latest.register("owner@example.com", "password123", "Owner", "Acme");
    });

    expect(authApiMock.register).toHaveBeenCalledWith({
      email: "owner@example.com",
      password: "password123",
      name: "Owner",
      organization_name: "Acme",
    });
    expect(latest.status).toBe("signedIn");
  });

  it("logout calls the API best-effort, clears the stored token, and signs out", async () => {
    secureStoreMock.getRefreshToken.mockResolvedValue("stored-refresh");
    authApiMock.refresh.mockResolvedValue(tokenPair());
    authApiMock.logout.mockResolvedValue(undefined);
    renderAuth();
    await waitFor(() => expect(latest.status).toBe("signedIn"));

    await act(async () => {
      await latest.logout();
    });

    expect(authApiMock.logout).toHaveBeenCalledWith("stored-refresh");
    expect(secureStoreMock.clearRefreshToken).toHaveBeenCalled();
    expect(latest.status).toBe("signedOut");
    expect(latest.user).toBeNull();
  });

  it("logout still signs out locally even if the API call fails", async () => {
    secureStoreMock.getRefreshToken.mockResolvedValue("stored-refresh");
    authApiMock.refresh.mockResolvedValue(tokenPair());
    authApiMock.logout.mockRejectedValue(new Error("network down"));
    renderAuth();
    await waitFor(() => expect(latest.status).toBe("signedIn"));

    await act(async () => {
      await latest.logout();
    });

    expect(latest.status).toBe("signedOut");
  });

  it("switchOrganization updates the current organization and role, and remembers the choice", async () => {
    secureStoreMock.getRefreshToken.mockResolvedValue("stored-refresh");
    authApiMock.refresh.mockResolvedValue(
      tokenPair({
        organizations: [
          { organization: ORG_A, role: "owner" },
          { organization: ORG_B, role: "member" },
        ],
      }),
    );
    renderAuth();
    await waitFor(() => expect(latest.status).toBe("signedIn"));

    act(() => {
      latest.switchOrganization(ORG_B.id);
    });

    expect(latest.currentOrganizationId).toBe(ORG_B.id);
    expect(latest.currentRole).toBe("member");
    expect(window.localStorage.getItem("vero.lastOrganizationId")).toBe(ORG_B.id);
  });

  it("switching organization clears the query cache; reselecting the same one does not", async () => {
    secureStoreMock.getRefreshToken.mockResolvedValue("stored-refresh");
    authApiMock.refresh.mockResolvedValue(
      tokenPair({
        organizations: [
          { organization: ORG_A, role: "owner" },
          { organization: ORG_B, role: "member" },
        ],
      }),
    );
    const queryClient = new QueryClient();
    renderAuth(queryClient);
    await waitFor(() => expect(latest.status).toBe("signedIn"));
    const clearSpy = vi.spyOn(queryClient, "clear");

    act(() => {
      latest.switchOrganization(ORG_A.id); // already selected -> no-op
    });
    expect(clearSpy).not.toHaveBeenCalled();

    act(() => {
      latest.switchOrganization(ORG_B.id);
    });
    expect(clearSpy).toHaveBeenCalledTimes(1);
  });

  it("changePassword rotates the token pair and keeps the session signed in", async () => {
    secureStoreMock.getRefreshToken.mockResolvedValue("stored-refresh");
    authApiMock.refresh.mockResolvedValue(tokenPair());
    authApiMock.changePassword.mockResolvedValue(tokenPair({ refresh_token: "rotated-refresh" }));
    renderAuth();
    await waitFor(() => expect(latest.status).toBe("signedIn"));

    await act(async () => {
      await latest.changePassword("old-pass", "new-password-1");
    });

    expect(authApiMock.changePassword).toHaveBeenCalledWith({
      current_password: "old-pass",
      new_password: "new-password-1",
    });
    expect(secureStoreMock.setRefreshToken).toHaveBeenCalledWith("rotated-refresh");
    expect(latest.status).toBe("signedIn");
  });

  it("refreshOrganizations re-fetches and falls back to another organization if the current one is gone", async () => {
    secureStoreMock.getRefreshToken.mockResolvedValue("stored-refresh");
    authApiMock.refresh.mockResolvedValue(tokenPair());
    const meResponse: MeResponse = { user: USER, organizations: [{ organization: ORG_B, role: "admin" }] };
    authApiMock.me.mockResolvedValue(meResponse);
    renderAuth();
    await waitFor(() => expect(latest.status).toBe("signedIn"));
    expect(latest.currentOrganizationId).toBe(ORG_A.id);

    await act(async () => {
      await latest.refreshOrganizations();
    });

    expect(latest.currentOrganizationId).toBe(ORG_B.id);
    expect(latest.currentRole).toBe("admin");
  });

  it("wires its refresh handler into authSession, so client.ts's 401 flow can sign a user out when the session can no longer be renewed", async () => {
    secureStoreMock.getRefreshToken.mockResolvedValue("stored-refresh");
    authApiMock.refresh.mockResolvedValueOnce(tokenPair()).mockRejectedValueOnce(new Error("expired"));
    renderAuth();
    await waitFor(() => expect(latest.status).toBe("signedIn"));

    await act(async () => {
      const token = await refreshAccessToken();
      expect(token).toBeNull();
    });

    expect(latest.status).toBe("signedOut");
  });
});
