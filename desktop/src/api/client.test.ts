import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient, ApiError, NetworkError } from "./client";
import { getDefaultApiBaseUrl } from "./config";

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
