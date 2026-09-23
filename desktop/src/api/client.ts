import { getAccessToken, getOrganizationId, refreshAccessToken } from "../auth/authSession";
import { getApiBaseUrl } from "./config";

const TIMEOUT_MS = 10_000;
// /auth/* never gets the automatic refresh-and-retry treatment: /login and /register need
// no session to begin with, and letting /refresh itself trigger a refresh on 401 would
// recurse into refreshAccessToken() while its own call is still in flight.
const AUTH_PATH_PREFIX = "/auth/";

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

async function fetchOnce(path: string, init?: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), TIMEOUT_MS);

  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const accessToken = getAccessToken();
  if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;
  const organizationId = getOrganizationId();
  if (organizationId) headers["X-Organization-Id"] = organizationId;

  try {
    return await fetch(`${getApiBaseUrl()}${path}`, {
      ...init,
      signal: controller.signal,
      headers: { ...headers, ...init?.headers },
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new NetworkError("Backend did not respond in time");
    }
    throw new NetworkError(err instanceof Error ? err.message : "Could not reach backend");
  } finally {
    clearTimeout(timeout);
  }
}

async function toResult<T>(response: Response): Promise<T> {
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetchOnce(path, init);

  // A 401 on an authenticated request means the access token has expired (it's normally
  // short-lived) rather than that the request was wrong — worth one silent retry after
  // renewing the session, rather than surfacing an error the user can't act on.
  if (response.status === 401 && !path.startsWith(AUTH_PATH_PREFIX) && getAccessToken() !== null) {
    const renewed = await refreshAccessToken();
    if (renewed !== null) {
      return toResult<T>(await fetchOnce(path, init));
    }
  }

  return toResult<T>(response);
}

export const apiClient = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};
