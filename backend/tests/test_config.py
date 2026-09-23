import pytest
from pydantic import ValidationError

from app.config import Settings

VALID_ENV = {
    "DATABASE_URL": "postgresql+psycopg://u:p@127.0.0.1:1/x",
    "CAMERA_CREDENTIALS_KEY": "test-key",
    "AUTH_SECRET_KEY": "x" * 32,
}


def _set(monkeypatch, **overrides):
    env = {**VALID_ENV, **overrides}
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)


def test_settings_require_database_url(monkeypatch):
    _set(monkeypatch, DATABASE_URL=None)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_require_camera_credentials_key(monkeypatch):
    _set(monkeypatch, CAMERA_CREDENTIALS_KEY=None)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_require_auth_secret_key(monkeypatch):
    _set(monkeypatch, AUTH_SECRET_KEY=None)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_reject_a_short_auth_secret_key(monkeypatch):
    _set(monkeypatch, AUTH_SECRET_KEY="too-short")
    with pytest.raises(ValidationError, match="at least 32 characters"):
        Settings(_env_file=None)


def test_settings_accept_an_auth_secret_key_at_exactly_the_minimum_length(monkeypatch):
    _set(monkeypatch, AUTH_SECRET_KEY="x" * 32)
    assert Settings(_env_file=None).auth_secret_key == "x" * 32


def test_settings_read_values_from_environment(monkeypatch):
    _set(monkeypatch)
    settings = Settings(_env_file=None)
    assert settings.database_url == VALID_ENV["DATABASE_URL"]
    assert settings.camera_credentials_key == "test-key"
    assert settings.auth_secret_key == "x" * 32


def test_token_ttls_have_sane_defaults_and_can_be_overridden(monkeypatch):
    _set(monkeypatch)
    defaults = Settings(_env_file=None)
    assert defaults.access_token_ttl_seconds == 15 * 60
    assert defaults.refresh_token_ttl_seconds == 30 * 24 * 60 * 60

    _set(monkeypatch, ACCESS_TOKEN_TTL_SECONDS="5", REFRESH_TOKEN_TTL_SECONDS="10")
    overridden = Settings(_env_file=None)
    assert overridden.access_token_ttl_seconds == 5
    assert overridden.refresh_token_ttl_seconds == 10


def test_trial_days_has_a_sane_default_and_can_be_overridden(monkeypatch):
    _set(monkeypatch)
    assert Settings(_env_file=None).trial_days == 3

    _set(monkeypatch, TRIAL_DAYS="7")
    assert Settings(_env_file=None).trial_days == 7
