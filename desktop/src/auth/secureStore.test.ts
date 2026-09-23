import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { clearRefreshToken, getRefreshToken, setRefreshToken } from "./secureStore";

vi.mock("@tauri-apps/api/core");

const isTauriMock = vi.mocked(isTauri);
const invokeMock = vi.mocked(invoke);

const FALLBACK_KEY = "vero.devRefreshToken";

describe("secureStore", () => {
  afterEach(() => {
    vi.resetAllMocks();
    window.localStorage.clear();
  });

  describe("outside a real Tauri window (plain-browser dev server / live checks)", () => {
    beforeEach(() => {
      isTauriMock.mockReturnValue(false);
    });

    it("returns null when nothing has been stored yet", async () => {
      expect(await getRefreshToken()).toBeNull();
      expect(invokeMock).not.toHaveBeenCalled();
    });

    it("round-trips a token through the clearly-labelled localStorage fallback key", async () => {
      await setRefreshToken("a-refresh-token");
      expect(window.localStorage.getItem(FALLBACK_KEY)).toBe("a-refresh-token");
      expect(await getRefreshToken()).toBe("a-refresh-token");
      expect(invokeMock).not.toHaveBeenCalled();
    });

    it("clears the stored token", async () => {
      await setRefreshToken("a-refresh-token");
      await clearRefreshToken();
      expect(await getRefreshToken()).toBeNull();
    });
  });

  describe("inside a real Tauri window", () => {
    beforeEach(() => {
      isTauriMock.mockReturnValue(true);
    });

    it("get delegates to the secret_get command for the refresh_token account", async () => {
      invokeMock.mockResolvedValue("stored-token");
      const result = await getRefreshToken();
      expect(invokeMock).toHaveBeenCalledWith("secret_get", { account: "refresh_token" });
      expect(result).toBe("stored-token");
    });

    it("set delegates to the secret_set command with the value", async () => {
      invokeMock.mockResolvedValue(undefined);
      await setRefreshToken("new-token");
      expect(invokeMock).toHaveBeenCalledWith("secret_set", { account: "refresh_token", value: "new-token" });
    });

    it("clear delegates to the secret_delete command", async () => {
      invokeMock.mockResolvedValue(undefined);
      await clearRefreshToken();
      expect(invokeMock).toHaveBeenCalledWith("secret_delete", { account: "refresh_token" });
    });

    it("never touches localStorage", async () => {
      invokeMock.mockResolvedValue(null);
      await getRefreshToken();
      expect(window.localStorage.getItem(FALLBACK_KEY)).toBeNull();
    });
  });
});
