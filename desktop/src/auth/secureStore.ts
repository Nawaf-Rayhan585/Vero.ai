/**
 * Where the desktop app keeps the refresh token: the OS credential store (Windows
 * Credential Manager), via three Rust commands (`desktop/src-tauri/src/secure_store.rs`)
 * — never a plain file, never the webview's localStorage, which any script running in the
 * page could read.
 *
 * Outside a real Tauri window (the plain-browser dev server this app's live checks run
 * against) there is no OS credential store to call into, so this falls back to
 * localStorage instead of failing outright — clearly labelled below, and never the path a
 * packaged build takes.
 */
import { invoke, isTauri } from "@tauri-apps/api/core";

const REFRESH_TOKEN_ACCOUNT = "refresh_token";
const BROWSER_FALLBACK_KEY = "vero.devRefreshToken";

function useBrowserFallback(): boolean {
  return !isTauri();
}

export async function getRefreshToken(): Promise<string | null> {
  if (useBrowserFallback()) {
    try {
      return window.localStorage.getItem(BROWSER_FALLBACK_KEY);
    } catch {
      return null;
    }
  }
  return invoke<string | null>("secret_get", { account: REFRESH_TOKEN_ACCOUNT });
}

export async function setRefreshToken(value: string): Promise<void> {
  if (useBrowserFallback()) {
    try {
      window.localStorage.setItem(BROWSER_FALLBACK_KEY, value);
    } catch {
      // Storage unavailable (private mode, blocked site data) — the session just won't
      // survive a restart; nothing to do about it here.
    }
    return;
  }
  await invoke("secret_set", { account: REFRESH_TOKEN_ACCOUNT, value });
}

export async function clearRefreshToken(): Promise<void> {
  if (useBrowserFallback()) {
    try {
      window.localStorage.removeItem(BROWSER_FALLBACK_KEY);
    } catch {
      // Nothing to clear if storage isn't available in the first place.
    }
    return;
  }
  await invoke("secret_delete", { account: REFRESH_TOKEN_ACCOUNT });
}
