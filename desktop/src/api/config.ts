const STORAGE_KEY = "vero.apiBaseUrl";
const DEFAULT_BASE_URL = "http://127.0.0.1:8000";

function readOverride(): string | null {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return value && value.trim() ? value.trim() : null;
  } catch {
    return null;
  }
}

/** Resolution order: localStorage override > VITE_API_BASE_URL > default. */
export function getApiBaseUrl(): string {
  return readOverride() || import.meta.env.VITE_API_BASE_URL || DEFAULT_BASE_URL;
}

export function setApiBaseUrlOverride(url: string | null): void {
  try {
    if (url && url.trim()) {
      window.localStorage.setItem(STORAGE_KEY, url.trim());
    } else {
      window.localStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    // localStorage unavailable (private mode, blocked storage) — override just won't persist.
  }
}

export function getDefaultApiBaseUrl(): string {
  return DEFAULT_BASE_URL;
}

export function isValidBaseUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}
