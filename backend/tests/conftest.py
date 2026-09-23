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
        conn.execute(
            text(
                "TRUNCATE TABLE jobs, cameras, lines, zones, events, heatmap_snapshots, "
                "refresh_tokens, memberships, locations, devices, subscriptions, organizations, users"
            )
        )


TEST_PASSWORD = "test-password-123"


def _register(test_client, email: str, organization_name: str = "Test Org", name: str = "Test User", password: str = TEST_PASSWORD):
    response = test_client.post(
        "/auth/register",
        json={"email": email, "password": password, "name": name, "organization_name": organization_name},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    test_client.headers["Authorization"] = f"Bearer {body['access_token']}"
    # Convenience, not part of the real API: the test's own user/org, and its refresh
    # token in case a test wants to exercise /auth/refresh or /auth/logout directly.
    test_client.test_user = body["user"]
    test_client.test_organization = body["organizations"][0]["organization"]
    test_client.test_refresh_token = body["refresh_token"]
    return test_client


@pytest.fixture
def anonymous_client():
    """The app with no Authorization header — for asserting that anonymous requests are
    rejected, and as the starting point for registering additional test accounts."""
    from fastapi.testclient import TestClient

    from main import app

    return TestClient(app)


@pytest.fixture
def register_user(anonymous_client):
    """Factory: registers a brand-new user + organization (each call's own, independent of
    the `client` fixture's) and returns an authenticated TestClient for them — for tests
    that need a *second* account: tenant isolation, roles, multi-organization membership."""
    from fastapi.testclient import TestClient

    from main import app

    def register(email: str, **kwargs):
        return _register(TestClient(app), email, **kwargs)

    return register


@pytest.fixture
def client(anonymous_client):
    """A backend client authenticated as a fresh test user who owns a fresh test
    organization (with its default "Main location"). Auth is universal now, so being
    logged in — not needing to log in — is the default most tests should assume."""
    return _register(anonymous_client, "owner@example.com")


@pytest.fixture
def add_member():
    """Factory: adds `member_client`'s user to `owner_client`'s organization with the given
    role (via the real API), and points `member_client` at that organization by default —
    a person can belong to several organizations (their own, from registering, plus this
    one), so without this their requests would otherwise hit the "which one did you mean"
    400 rather than the role check a test is actually trying to exercise."""

    def add(owner_client, member_client, role="member"):
        response = owner_client.post("/members", json={"email": member_client.test_user["email"], "role": role})
        assert response.status_code == 200, response.text
        member_client.headers["X-Organization-Id"] = owner_client.test_organization["id"]
        return response.json()

    return add


@pytest.fixture
def db_session():
    from app.database import SessionLocal

    with SessionLocal() as session:
        yield session


@pytest.fixture
def panning_video(tmp_path):
    """A short video that pans a cropped window across the real bus.jpg photo. Every pixel
    stays genuinely real, only what's visible in-frame shifts, which was verified by hand
    (see docs/ROADMAP.md's Phase 6 notes) to produce stable YOLO+ByteTrack track IDs whose
    position shifts monotonically — a realistic "someone is walking" analogue. A video of
    a static image can't exercise anything that depends on movement, and pasting a person
    crop onto a plain background produces zero detections (confirmed empirically).

    Returns (path, frame_width, frame_height).
    """
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


@pytest.fixture
def scan_scene():
    """Factory for a synthetic 720p frame containing real, decodable QR codes / barcodes
    (generated with zxing-cpp's own writer) and real rendered text for OCR, any subset of
    them. Sized so each code is comfortably readable: a CCTV frame only decodes codes that
    span enough pixels (~200 px wide worked when measured; 120 px did not).
    """
    import cv2
    import numpy as np
    import zxingcpp

    formats = zxingcpp.BarcodeFormat

    def code_image(fmt, value, scale):
        image = np.array(zxingcpp.write_barcode_to_image(zxingcpp.create_barcode(value, fmt), scale=scale))
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR) if image.ndim == 2 else image

    def build(qr=None, barcode=None, barcode_format=None, text=None, width=1280, height=720):
        frame = np.full((height, width, 3), 90, np.uint8)
        if qr is not None:
            image = code_image(formats.QRCode, qr, 8)
            frame[80 : 80 + image.shape[0], 100 : 100 + image.shape[1]] = image
        if barcode is not None:
            image = code_image(barcode_format or formats.Code128, barcode, 4)
            frame[120 : 120 + image.shape[0], 600 : 600 + image.shape[1]] = image
        if text is not None:
            cv2.putText(frame, text, (100, 620), cv2.FONT_HERSHEY_SIMPLEX, 2.2, (255, 255, 255), 4)
        return frame

    return build


@pytest.fixture
def scan_video(tmp_path, scan_scene):
    """A short video of a scene holding a QR code, a Code 128 barcode and a line of text.
    Nothing in it moves, and nothing in it needs a detector. Returns the video's path
    together with the values it contains."""
    from types import SimpleNamespace

    import cv2

    contents = SimpleNamespace(qr="https://vero.ai/t/42", barcode="PKG-99812", text="PALLET 4471-B")
    frame = scan_scene(qr=contents.qr, barcode=contents.barcode, text=contents.text)
    video_path = tmp_path / "scan-feed.avi"
    writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"MJPG"), 5.0, (frame.shape[1], frame.shape[0]))
    assert writer.isOpened()
    for _ in range(15):
        writer.write(frame)
    writer.release()
    contents.path = str(video_path)
    return contents


@pytest.fixture
def add_event(db_session):
    """Factory: inserts one event row directly, with a chosen timestamp, and returns it.
    Analytics tests seed their data this way so the expected numbers are exact and known."""
    import uuid

    from app.models import Event

    def add(camera_id, event_type, at, **fields):
        row = Event(camera_id=uuid.UUID(str(camera_id)), event_type=event_type, occurred_at=at, **fields)
        db_session.add(row)
        db_session.commit()
        return row

    return add


@pytest.fixture
def add_heat(db_session):
    """Factory: inserts one hourly heatmap snapshot. cells maps (row, col) -> heat count."""
    import uuid

    import numpy as np

    from app.heatmap import encode_grid
    from app.models import HeatmapSnapshot

    def add(camera_id, period_start, cells, frame=(800, 400), grid_width=80, grid_height=40):
        grid = np.zeros((grid_height, grid_width), dtype=np.uint32)
        for (row, col), count in cells.items():
            grid[row, col] = count
        snapshot = HeatmapSnapshot(
            camera_id=uuid.UUID(str(camera_id)),
            period_start=period_start,
            frame_width=frame[0],
            frame_height=frame[1],
            grid_width=grid_width,
            grid_height=grid_height,
            cells=encode_grid(grid),
            sample_count=int(grid.sum()),
        )
        db_session.add(snapshot)
        db_session.commit()
        return snapshot

    return add
