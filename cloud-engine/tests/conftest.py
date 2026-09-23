"""cloud-engine's own test suite. Runs against the SAME shared PostgreSQL test database
backend's suite uses (docs/ARCHITECTURE.md: one shared database, not one per service) —
migrated with backend's own Alembic head, reached via the same sys.path insertion
main.py itself uses to import app.*. This deliberately re-implements (not imports)
backend/tests/conftest.py's test-database setup: importing another suite's conftest.py
as a plain module is a documented gotcha (pytest's own conftest collection conflicts
with it), so the ~15 lines of setup are duplicated here instead.

The DATABASE_URL environment variable is pointed at the test database at import time,
before any application module creates its engine, so the dev database is never touched.
"""
import os
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

CLOUD_ENGINE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = CLOUD_ENGINE_DIR.parent
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(CLOUD_ENGINE_DIR))

from app.config import Settings  # noqa: E402

_dev_url = make_url(Settings().database_url)
TEST_DB_NAME = f"{_dev_url.database}_test"
_test_url = _dev_url.set(database=TEST_DB_NAME)
os.environ["DATABASE_URL"] = _test_url.render_as_string(hide_password=False)


def _alembic_config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return config


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

    command.upgrade(_alembic_config(), "head")
    yield


@pytest.fixture(autouse=True)
def clean_tables(test_database):
    from app.database import engine

    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE TABLE jobs, cameras, lines, zones, events, heatmap_snapshots, "
                "refresh_tokens, memberships, locations, devices, subscriptions, organizations, users"
            )
        )


@pytest.fixture
def internal_secret():
    from app.config import get_settings

    secret = get_settings().cloud_engine_internal_secret
    assert secret, "CLOUD_ENGINE_INTERNAL_SECRET must be set in .env to run cloud-engine's tests"
    return secret


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


def _make_camera(db_session, *, plan_type, rtsp_url="rtsp://127.0.0.1:1/unused"):
    from datetime import datetime, timedelta, timezone

    from app.models import Camera, Location, Organization, Subscription

    org = Organization(name=f"{plan_type or 'no-plan'} Org")
    db_session.add(org)
    db_session.flush()
    db_session.add(
        Subscription(
            organization_id=org.id,
            status="active",
            plan_type=plan_type,
            trial_started_at=datetime.now(timezone.utc),
            trial_ends_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
    )
    location = Location(organization_id=org.id, name="Main")
    db_session.add(location)
    db_session.flush()
    camera = Camera(location_id=location.id, name="Cam", rtsp_url=rtsp_url)
    db_session.add(camera)
    db_session.commit()
    db_session.refresh(camera)
    return camera


@pytest.fixture
def vero_cloud_camera(db_session):
    """A camera belonging to a fresh organization on the vero_cloud plan — the only kind
    of camera cloud-engine's endpoints should actually process a request for."""
    return _make_camera(db_session, plan_type="vero_cloud")


@pytest.fixture
def own_hardware_camera(db_session):
    """A camera belonging to an organization NOT on the vero_cloud plan — cloud-engine
    must refuse to process it even if asked to (defense in depth: backend should never
    proxy this camera here, but cloud-engine doesn't blindly trust that it won't)."""
    return _make_camera(db_session, plan_type="own_hardware")


@pytest.fixture
def panning_video(tmp_path):
    """Identical to backend/tests/conftest.py's fixture of the same name — see there for
    why this specific video (not a static image) is needed to exercise real motion."""
    import cv2
    from ultralytics.utils import ASSETS

    image = cv2.imread(str(ASSETS / "bus.jpg"))
    height, width = image.shape[:2]
    pad = 300
    padded = cv2.copyMakeBorder(image, 0, 0, pad, pad, cv2.BORDER_REPLICATE)

    n_frames = 30
    video_path = tmp_path / "panning-feed.avi"
    writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"MJPG"), 5.0, (width, height))
    assert writer.isOpened()
    for i in range(n_frames):
        x_start = int(i * (2 * pad) / (n_frames - 1))
        writer.write(padded[:, x_start : x_start + width])
    writer.release()
    return str(video_path), width, height
