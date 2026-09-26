"""Phase 16: what the "VeroAiBackend" Windows Service (registered by
src-tauri/windows/hooks.nsi via NSSM) actually runs — never invoked directly in dev,
where `python -m uvicorn main:app --reload` is still what you want.

Self-migrating on every service start, not a one-time installer step: an app upgrade
re-install restarts this service, and whatever new migrations shipped with it need to
apply before Uvicorn (and therefore the desktop app) can talk to the database. Alembic's
own upgrade is a no-op when already at head, so this is safe to run on every single
start, not just the first one after a fresh install.

Exits non-zero (rather than starting a broken Uvicorn) if migrations fail — NSSM sees the
non-zero exit and, per its own configured restart policy, retries; a customer with a
Postgres genuinely down sees the service failing to start, not a backend that's "up" but
can't actually do anything.
"""
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

BACKEND_DIR = Path(__file__).resolve().parent


def _alembic_config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return config


def main() -> None:
    try:
        command.upgrade(_alembic_config(), "head")
    except Exception as exc:  # noqa: BLE001 - deliberately broad: any migration failure must stop the service
        print(f"Migration failed, not starting the backend: {exc}", file=sys.stderr)
        sys.exit(1)

    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
