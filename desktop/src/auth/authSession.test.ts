import { afterEach, describe, expect, it, vi } from "vitest";
import {
  clearSession,
  configureSessionRefresh,
  getAccessToken,
  getOrganizationId,
  refreshAccessToken,
  setAccessToken,
  setOrganizationId,
} from "./authSession";

describe("authSession", () => {
  afterEach(() => {
    clearSession();
    vi.restoreAllMocks();
  });

  it("holds the access token and organization id set into it", () => {
    setAccessToken("token-a");
    setOrganizationId("org-a");
    expect(getAccessToken()).toBe("token-a");
    expect(getOrganizationId()).toBe("org-a");
  });

  it("clearSession resets both to null", () => {
    setAccessToken("token-a");
    setOrganizationId("org-a");
    clearSession();
    expect(getAccessToken()).toBeNull();
    expect(getOrganizationId()).toBeNull();
  });

  it("refreshAccessToken returns null and does nothing when no refresh handler was configured", async () => {
    expect(await refreshAccessToken()).toBeNull();
  });

  it("refreshAccessToken returns the renewed token on success and does not call onExpired", async () => {
    const refresh = vi.fn().mockResolvedValue("renewed-token");
    const onExpired = vi.fn();
    configureSessionRefresh({ refresh, onExpired });

    expect(await refreshAccessToken()).toBe("renewed-token");
    expect(onExpired).not.toHaveBeenCalled();
  });

  it("refreshAccessToken calls onExpired and returns null when the handler reports failure", async () => {
    const refresh = vi.fn().mockResolvedValue(null);
    const onExpired = vi.fn();
    configureSessionRefresh({ refresh, onExpired });

    expect(await refreshAccessToken()).toBeNull();
    expect(onExpired).toHaveBeenCalledTimes(1);
  });

  it("concurrent calls share a single in-flight refresh instead of racing to renew twice", async () => {
    let resolveRefresh!: (token: string | null) => void;
    const refresh = vi.fn(
      () =>
        new Promise<string | null>((resolve) => {
          resolveRefresh = resolve;
        }),
    );
    configureSessionRefresh({ refresh, onExpired: vi.fn() });

    const first = refreshAccessToken();
    const second = refreshAccessToken();
    resolveRefresh("shared-token");

    expect(await first).toBe("shared-token");
    expect(await second).toBe("shared-token");
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("a later call starts a fresh refresh once the previous one has settled", async () => {
    const refresh = vi.fn().mockResolvedValueOnce("token-1").mockResolvedValueOnce("token-2");
    configureSessionRefresh({ refresh, onExpired: vi.fn() });

    expect(await refreshAccessToken()).toBe("token-1");
    expect(await refreshAccessToken()).toBe("token-2");
    expect(refresh).toHaveBeenCalledTimes(2);
  });
});
