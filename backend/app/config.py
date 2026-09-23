from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]

MIN_AUTH_SECRET_KEY_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    database_url: str
    camera_credentials_key: str
    # Signs access/refresh tokens (app/security.py). Required, no default: Development
    # Rule 12 ("no hardcoded secrets") applies to auth even more than to most things.
    auth_secret_key: str
    access_token_ttl_seconds: int = 15 * 60
    refresh_token_ttl_seconds: int = 30 * 24 * 60 * 60
    # V1-SCOPE.md: "3-day free trial (enforced server-side)". Not a secret, so a plain
    # default rather than a required .env value.
    trial_days: int = 3
    # Phase 13: where cloud-engine listens, and the shared secret it checks requests
    # against (app/cloud_routing.py). Both optional — most dev/test setups never touch
    # Vero Cloud, so they shouldn't need to configure it just to run the app or the suite.
    # A camera on a "vero_cloud" organization gets a clear 503 if either is unset, rather
    # than silently running locally.
    cloud_engine_base_url: Optional[str] = None
    cloud_engine_internal_secret: Optional[str] = None

    @field_validator("auth_secret_key")
    @classmethod
    def _validate_auth_secret_key(cls, value: str) -> str:
        if len(value) < MIN_AUTH_SECRET_KEY_LENGTH:
            raise ValueError(
                f"AUTH_SECRET_KEY must be at least {MIN_AUTH_SECRET_KEY_LENGTH} characters. Generate one with:\n"
                '  python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
