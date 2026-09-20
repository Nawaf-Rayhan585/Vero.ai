import pytest
from pydantic import ValidationError

from app.config import Settings


def test_settings_require_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("CAMERA_CREDENTIALS_KEY", "test-key")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_require_camera_credentials_key(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@127.0.0.1:1/x")
    monkeypatch.delenv("CAMERA_CREDENTIALS_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_read_values_from_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@127.0.0.1:1/x")
    monkeypatch.setenv("CAMERA_CREDENTIALS_KEY", "test-key")
    settings = Settings(_env_file=None)
    assert settings.database_url == "postgresql+psycopg://u:p@127.0.0.1:1/x"
    assert settings.camera_credentials_key == "test-key"
