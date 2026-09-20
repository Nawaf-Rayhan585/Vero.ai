import { getApiBaseUrl } from "./config";

const TIMEOUT_MS = 10_000;

export class ApiError extends Error {
  constructor(public status: number, public statusText: string, message?: string) {
    super(message || `Server returned ${status}`);
    this.name = "ApiError";
  }
}

export class NetworkError extends Error {
  constructor(message = "Could not reach backend") {
    super(message);
    this.name = "NetworkError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), TIMEOUT_MS);

  let response: Response;
  try {
    response = await fetch(`${getApiBaseUrl()}${path}`, {
      ...init,
      signal: controller.signal,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new NetworkError("Backend did not respond in time");
    }
    throw new NetworkError(err instanceof Error ? err.message : "Could not reach backend");
  } finally {
    clearTimeout(timeout);
  }

  if (!response.ok) {
    let detail: string | undefined;
    try {
      detail = (await response.json())?.detail;
    } catch {
      // response body wasn't JSON — fall back to the status text below.
    }
    throw new ApiError(response.status, response.statusText, detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const apiClient = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};
