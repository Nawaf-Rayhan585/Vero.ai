import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient, ApiError, NetworkError } from "./client";
import { getDefaultApiBaseUrl } from "./config";
import { clearSession, configureSessionRefresh, setAccessToken, setOrganizationId } from "../auth/authSession";

describe("apiClient", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("GET builds the URL from the base URL and path, and returns parsed JSON", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ status: "ok" }), { status: 200 }),
    );

    const result = await apiClient.get<{ status: string }>("/health");

    expect(fetchMock).toHaveBeenCalledWith(
      `${getDefaultApiBaseUrl()}/health`,
      expect.objectContaining({ headers: expect.objectContaining({ "Content-Type": "application/json" }) }),
    );
    expect(result).toEqual({ status: "ok" });
  });

  it("POST sends a JSON body", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ id: "abc" }), { status: 200 }));

    await apiClient.post("/jobs", { video_source: "a.jpg" });

    const [, init] = fetchMock.mock.calls[0];
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify({ video_source: "a.jpg" }));
  });

  it("throws ApiError with the response detail on a non-OK response", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "Job not found" }), { status: 404, statusText: "Not Found" }),
    );

    await expect(apiClient.get("/jobs/missing")).rejects.toMatchObject({
      name: "ApiError",
      status: 404,
      message: "Job not found",
    });
  });

  it("throws ApiError with a default message when the error body isn't JSON", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(new Response("oops", { status: 500, statusText: "Server Error" }));

    await expect(apiClient.get("/jobs")).rejects.toBeInstanceOf(ApiError);
  });

  it("throws NetworkError when fetch itself rejects", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));

    await expect(apiClient.get("/health")).rejects.toBeInstanceOf(NetworkError);
  });
});

describe("apiClient auth headers and 401 retry", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    clearSession();
  });

  it("does not send Authorization or X-Organization-Id when signed out", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({}), { status: 200 }));

    await apiClient.get("/cameras");

    const [, init] = fetchMock.mock.calls[0];
    const headers = init?.headers as Record<string, string>;
    expect(headers["Authorization"]).toBeUndefined();
    expect(headers["X-Organization-Id"]).toBeUndefined();
  });

  it("sends Authorization and X-Organization-Id once a session is set", async () => {
    setAccessToken("access-123");
    setOrganizationId("org-456");
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({}), { status: 200 }));

    await apiClient.get("/cameras");

    const [, init] = fetchMock.mock.calls[0];
    const headers = init?.headers as Record<string, string>;
    expect(headers["Authorization"]).toBe("Bearer access-123");
    expect(headers["X-Organization-Id"]).toBe("org-456");
  });

  it("on a 401, refreshes exactly once and retries the original request", async () => {
    setAccessToken("stale-token");
    const refresh = vi.fn().mockImplementation(async () => {
      setAccessToken("fresh-token");
      return "fresh-token";
    });
    configureSessionRefresh({ refresh, onExpired: vi.fn() });

    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: "expired" }), { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200 }));

    const result = await apiClient.get<{ ok: boolean }>("/cameras");

    expect(refresh).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    // The retried request carries the newly-renewed token, not the stale one.
    const [, secondInit] = fetchMock.mock.calls[1];
    expect((secondInit?.headers as Record<string, string>)["Authorization"]).toBe("Bearer fresh-token");
    expect(result).toEqual({ ok: true });
  });

  it("surfaces the original 401 when the refresh attempt itself fails", async () => {
    setAccessToken("stale-token");
    const refresh = vi.fn().mockResolvedValue(null);
    configureSessionRefresh({ refresh, onExpired: vi.fn() });

    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ detail: "expired" }), { status: 401 }));

    await expect(apiClient.get("/cameras")).rejects.toMatchObject({ status: 401 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("never retries a 401 from /auth/* paths (would recurse into the refresh call itself)", async () => {
    setAccessToken("stale-token");
    const refresh = vi.fn();
    configureSessionRefresh({ refresh, onExpired: vi.fn() });

    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ detail: "bad credentials" }), { status: 401 }));

    await expect(apiClient.post("/auth/login", {})).rejects.toMatchObject({ status: 401 });
    expect(refresh).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("does not attempt a refresh on a 401 when there was no access token to begin with", async () => {
    const refresh = vi.fn();
    configureSessionRefresh({ refresh, onExpired: vi.fn() });

    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ detail: "unauthorized" }), { status: 401 }));

    await expect(apiClient.get("/cameras")).rejects.toMatchObject({ status: 401 });
    expect(refresh).not.toHaveBeenCalled();
  });
});
