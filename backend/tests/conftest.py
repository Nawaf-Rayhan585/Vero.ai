"""Test fixtures. Tests run against a real PostgreSQL database named "<dev db>_test".

The DATABASE_URL environment variable is pointed at the test database at import time,
before any application module creates its engine, so the dev database is never touched.
"""
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

from app.config import Settings

BACKEND_DIR = Path(__file__).resolve().parents[1]

_dev_url = make_url(Settings().database_url)
TEST_DB_NAME = f"{_dev_url.database}_test"
_test_url = _dev_url.set(database=TEST_DB_NAME)
os.environ["DATABASE_URL"] = _test_url.render_as_string(hide_password=False)


def alembic_config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return config


@pytest.fixture
def alembic_cfg() -> Config:
    return alembic_config()


@pytest.fixture(scope="session", autouse=True)
def test_database():
    assert TEST_DB_NAME.endswith("_test"), "refusing to run tests against a non-test database"
    admin = create_engine(_dev_url, isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 5})
    try:
        with admin.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": TEST_DB_NAME}
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    except OperationalError as exc:
        pytest.exit(
            "PostgreSQL is not reachable. Start it from the repo root with "
            f"'docker compose up -d postgres --wait' and re-run the tests.\n{exc}",
            returncode=2,
        )
    finally:
        admin.dispose()

    command.upgrade(alembic_config(), "head")
    yield


@pytest.fixture(autouse=True)
def clean_tables(test_database):
    from app.database import engine

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE jobs, cameras, lines"))


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from main import app

    return TestClient(app)


@pytest.fixture
def db_session():
    from app.database import SessionLocal

    with SessionLocal() as session:
        yield session
