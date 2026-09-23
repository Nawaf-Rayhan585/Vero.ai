"""Vero Cloud's AI engine (Phase 13) — a service separate from backend/, for
organizations on the "vero_cloud" plan. Reuses backend's tracking/counting/zones/
heatmap/scanning/camera_testing/crypto/events code directly, via the same
sys.path-insertion pattern backend/app/detection_runner.py already uses to import
ai-engine/detector.py — not a copy of that code, and not its own database or config:
this process shares backend's PostgreSQL database and its app.config.Settings (the same
repo-root .env). There is no separate "cloud database."

This service is reached only by backend itself (app/cloud_routing.py) — never by the
desktop app or the internet directly. In a real deployment it would sit on a private
network; here, auth is a single shared secret (X-Internal-Secret), not JWT/OrgContext.
"""
import dataclasses
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import cv2
from fastapi import Depends, FastAPI, Header, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app import camera_testing  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.counting import LineConfig, Point  # noqa: E402
from app.crypto import decrypt_password  # noqa: E402
from app.database import get_db  # noqa: E402
from app.events import close_dangling_sessions, event_recorder  # noqa: E402
from app.models import Camera, Line, Organization, Zone  # noqa: E402
from app.schemas import CameraRead, TrackingStatusRead, camera_to_read  # noqa: E402
from app.tracking import TrackingStatusSnapshot, tracking_manager  # noqa: E402
from app.zones import ZoneConfig  # noqa: E402


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Same startup/shutdown lifecycle as backend/main.py's, reused directly — a session a
    # crash left "running" gets closed on startup, and every session is stopped (flushing
    # its final events/heat) before the process actually exits.
    close_dangling_sessions()
    yield
    tracking_manager.stop_all()
    event_recorder.stop()


app = FastAPI(lifespan=lifespan)

_STOPPED_SNAPSHOT = TrackingStatusRead(status="stopped", frame_count=0, active_track_ids=[])


def _to_status_read(snapshot: TrackingStatusSnapshot) -> TrackingStatusRead:
    return TrackingStatusRead(**dataclasses.asdict(snapshot))


def _decrypted_credentials(camera: Camera) -> tuple[Optional[str], Optional[str]]:
    password = decrypt_password(camera.encrypted_password) if camera.encrypted_password else None
    return camera.username, password


def require_internal_secret(x_internal_secret: Optional[str] = Header(default=None)) -> None:
    settings = get_settings()
    if not settings.cloud_engine_internal_secret or x_internal_secret != settings.cloud_engine_internal_secret:
        raise HTTPException(status_code=401, detail="Not authenticated")


def _get_cloud_camera_or_404(db: Session, camera_id: str) -> Camera:
    """No OrgContext here — this service is never reached by a signed-in user directly;
    backend has already proven the caller may act on this camera before ever proxying
    here. Still confirms the camera's organization is actually on the Vero Cloud plan, as
    a defense-in-depth check against a routing bug in backend, not a trust boundary."""
    try:
        parsed_id = uuid.UUID(camera_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Camera not found")
    camera = db.scalar(select(Camera).where(Camera.id == parsed_id))
    if camera is None or camera.location is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    organization = db.get(Organization, camera.location.organization_id)
    sub = organization.subscription if organization else None
    if sub is None or sub.plan_type != "vero_cloud":
        raise HTTPException(status_code=403, detail="This camera's organization is not on the Vero Cloud plan")
    return camera


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post(
    "/cameras/{camera_id}/tracking/start",
    response_model=TrackingStatusRead,
    dependencies=[Depends(require_internal_secret)],
)
def start_tracking(camera_id: str, db: Session = Depends(get_db)):
    camera = _get_cloud_camera_or_404(db, camera_id)
    username, password = _decrypted_credentials(camera)
    rows = db.scalars(select(Line).where(Line.camera_id == camera.id)).all()
    lines = [LineConfig(id=row.id, name=row.name, x1=row.x1, y1=row.y1, x2=row.x2, y2=row.y2) for row in rows]
    zone_rows = db.scalars(select(Zone).where(Zone.camera_id == camera.id)).all()
    zones = [
        ZoneConfig(id=row.id, name=row.name, points=tuple(Point(p["x"], p["y"]) for p in row.points))
        for row in zone_rows
    ]
    if not camera.enabled_modules:
        raise HTTPException(
            status_code=422,
            detail="Enable at least one AI module for this camera before starting tracking",
        )
    session = tracking_manager.start(
        camera.id, camera.rtsp_url, username, password, lines, zones, camera.enabled_modules, event_recorder
    )
    return _to_status_read(session.snapshot())


@app.post(
    "/cameras/{camera_id}/tracking/stop",
    response_model=TrackingStatusRead,
    dependencies=[Depends(require_internal_secret)],
)
def stop_tracking(camera_id: str, db: Session = Depends(get_db)):
    camera = _get_cloud_camera_or_404(db, camera_id)
    tracking_manager.stop(camera.id)
    return _STOPPED_SNAPSHOT


@app.get(
    "/cameras/{camera_id}/tracking/status",
    response_model=TrackingStatusRead,
    dependencies=[Depends(require_internal_secret)],
)
def get_tracking_status(camera_id: str, db: Session = Depends(get_db)):
    camera = _get_cloud_camera_or_404(db, camera_id)
    session = tracking_manager.get(camera.id)
    if session is None:
        return _STOPPED_SNAPSHOT
    return _to_status_read(session.snapshot())


@app.get("/cameras/{camera_id}/tracking/latest-frame", dependencies=[Depends(require_internal_secret)])
def get_latest_tracking_frame(camera_id: str, heatmap: bool = False, db: Session = Depends(get_db)):
    camera = _get_cloud_camera_or_404(db, camera_id)
    session = tracking_manager.get(camera.id)
    if session is None:
        raise HTTPException(status_code=404, detail="Tracking has not been started for this camera")
    frame = session.latest_frame(heatmap=heatmap)
    if frame is None:
        raise HTTPException(status_code=503, detail="No frame available yet")
    return Response(content=frame, media_type="image/jpeg")


@app.post(
    "/cameras/{camera_id}/test-connection",
    response_model=CameraRead,
    dependencies=[Depends(require_internal_secret)],
)
def test_camera_connection(camera_id: str, db: Session = Depends(get_db)):
    camera = _get_cloud_camera_or_404(db, camera_id)
    username, password = _decrypted_credentials(camera)
    outcome = camera_testing.test_connection(camera.rtsp_url, username, password)

    camera.connection_status = "online" if outcome.online else "offline"
    camera.last_tested_at = datetime.now(timezone.utc)
    camera.last_error = outcome.error
    camera.last_fps = outcome.fps
    camera.last_width = outcome.width
    camera.last_height = outcome.height
    db.commit()
    return camera_to_read(camera)


@app.get("/cameras/{camera_id}/snapshot", dependencies=[Depends(require_internal_secret)])
def get_camera_snapshot(camera_id: str, db: Session = Depends(get_db)):
    camera = _get_cloud_camera_or_404(db, camera_id)
    username, password = _decrypted_credentials(camera)
    result = camera_testing.grab_snapshot(camera.rtsp_url, username, password)

    if result.frame is None:
        raise HTTPException(status_code=503, detail=result.error or "Camera unavailable")

    ok, encoded = cv2.imencode(".jpg", result.frame)
    if not ok:
        raise HTTPException(status_code=503, detail="Failed to encode snapshot")
    return Response(content=encoded.tobytes(), media_type="image/jpeg")
