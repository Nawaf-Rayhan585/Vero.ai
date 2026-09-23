//! Stores the desktop session's refresh token in the OS credential store — the Windows
//! Credential Manager, via the `keyring` crate's native backend — rather than in a plain
//! file or in the webview's localStorage, which any script running in the page could read.
//!
//! One entry per purpose: service `ai.vero.desktop`, account `refresh_token`. Tauri's own
//! app identifier is reused as the service name so this can't collide with an unrelated
//! app's entry on the same machine.

use keyring::Entry;

const SERVICE: &str = "ai.vero.desktop";
const REFRESH_TOKEN_ACCOUNT: &str = "refresh_token";

fn entry_for(account: &str) -> Result<Entry, String> {
    Entry::new(SERVICE, account).map_err(|e| e.to_string())
}

/// Stores `value` under `account`, overwriting whatever was there before.
#[tauri::command]
pub fn secret_set(account: String, value: String) -> Result<(), String> {
    entry_for(&account)?.set_password(&value).map_err(|e| e.to_string())
}

/// Returns the stored value, or `None` if nothing has been set — not an error, since "no
/// saved session" is the normal state on first launch and after signing out.
#[tauri::command]
pub fn secret_get(account: String) -> Result<Option<String>, String> {
    match entry_for(&account)?.get_password() {
        Ok(value) => Ok(Some(value)),
        Err(keyring::Error::NoEntry) => Ok(None),
        Err(e) => Err(e.to_string()),
    }
}

/// Removes the stored value. Deleting something that was never set is not an error either
/// — sign-out calls this unconditionally.
#[tauri::command]
pub fn secret_delete(account: String) -> Result<(), String> {
    match entry_for(&account)?.delete_credential() {
        Ok(()) => Ok(()),
        Err(keyring::Error::NoEntry) => Ok(()),
        Err(e) => Err(e.to_string()),
    }
}

/// The account name the desktop app actually uses for the refresh token, exposed so the
/// frontend doesn't have to hardcode it in two places.
#[tauri::command]
pub fn refresh_token_account() -> &'static str {
    REFRESH_TOKEN_ACCOUNT
}

#[cfg(test)]
mod tests {
    use super::*;

    // These exercise the *real* Windows Credential Manager (the `keyring` crate's v1 API
    // has no mock store to link against instead) — a distinct service name and a
    // per-test account keep them from colliding with the real app entry or each other,
    // and each test cleans up after itself.
    const TEST_SERVICE: &str = "ai.vero.desktop.test";

    fn test_entry(account: &str) -> Entry {
        Entry::new(TEST_SERVICE, account).expect("credential store available for tests")
    }

    fn cleanup(account: &str) {
        let _ = test_entry(account).delete_credential();
    }

    #[test]
    fn set_then_get_round_trips() {
        let account = "set_then_get_round_trips";
        cleanup(account);
        test_entry(account).set_password("abc123").unwrap();

        assert_eq!(test_entry(account).get_password().unwrap(), "abc123");

        cleanup(account);
    }

    #[test]
    fn get_before_set_is_no_entry() {
        let account = "get_before_set_is_no_entry";
        cleanup(account);

        assert!(matches!(test_entry(account).get_password(), Err(keyring::Error::NoEntry)));
    }

    #[test]
    fn delete_then_get_is_no_entry() {
        let account = "delete_then_get_is_no_entry";
        test_entry(account).set_password("abc123").unwrap();

        test_entry(account).delete_credential().unwrap();

        assert!(matches!(test_entry(account).get_password(), Err(keyring::Error::NoEntry)));
    }

    #[test]
    fn set_overwrites_a_previous_value() {
        let account = "set_overwrites_a_previous_value";
        cleanup(account);
        test_entry(account).set_password("first").unwrap();

        test_entry(account).set_password("second").unwrap();

        assert_eq!(test_entry(account).get_password().unwrap(), "second");

        cleanup(account);
    }

    // -- the command wrappers themselves (secret_get's NoEntry -> None mapping, etc.) --
    // These use the *real* service name deliberately, since that's the code path the app
    // actually runs; a leftover value from a previous run is cleared first, then restored.

    #[test]
    fn commands_round_trip_and_map_no_entry_to_none() {
        let account = "commands_round_trip_and_map_no_entry_to_none_test_account";
        let _ = secret_delete(account.to_string());

        assert_eq!(secret_get(account.to_string()).unwrap(), None);

        secret_set(account.to_string(), "token-value".to_string()).unwrap();
        assert_eq!(secret_get(account.to_string()).unwrap(), Some("token-value".to_string()));

        secret_delete(account.to_string()).unwrap();
        assert_eq!(secret_get(account.to_string()).unwrap(), None);

        // A second delete is still not an error.
        secret_delete(account.to_string()).unwrap();
    }

    #[test]
    fn the_refresh_token_account_name_is_stable() {
        assert_eq!(refresh_token_account(), "refresh_token");
    }
}
