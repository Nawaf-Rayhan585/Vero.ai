import dataclasses

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.counting import LineConfig, Point
from app.database import get_db
from app.events import event_recorder
from app.models import Line, Zone
from app.routers.cameras import _decrypted_credentials, _get_camera_or_404
from app.schemas import TrackingStatusRead
from app.tracking import TrackingStatusSnapshot, tracking_manager
from app.zones import ZoneConfig

router = APIRouter(prefix="/cameras", tags=["tracking"])

_STOPPED_SNAPSHOT = TrackingStatusRead(status="stopped", frame_count=0, active_track_ids=[])


def _to_status_read(snapshot: TrackingStatusSnapshot) -> TrackingStatusRead:
    return TrackingStatusRead(**dataclasses.asdict(snapshot))


@router.post("/{camera_id}/tracking/start", response_model=TrackingStatusRead)
def start_tracking(camera_id: str, db: Session = Depends(get_db)):
    camera = _get_camera_or_404(db, camera_id)
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


@router.post("/{camera_id}/tracking/stop", response_model=TrackingStatusRead)
def stop_tracking(camera_id: str, db: Session = Depends(get_db)):
    camera = _get_camera_or_404(db, camera_id)
    tracking_manager.stop(camera.id)
    return _STOPPED_SNAPSHOT


@router.get("/{camera_id}/tracking/status", response_model=TrackingStatusRead)
def get_tracking_status(camera_id: str, db: Session = Depends(get_db)):
    camera = _get_camera_or_404(db, camera_id)
    session = tracking_manager.get(camera.id)
    if session is None:
        return _STOPPED_SNAPSHOT
    return _to_status_read(session.snapshot())


@router.get("/{camera_id}/tracking/latest-frame")
def get_latest_tracking_frame(camera_id: str, heatmap: bool = False, db: Session = Depends(get_db)):
    camera = _get_camera_or_404(db, camera_id)
    session = tracking_manager.get(camera.id)
    if session is None:
        raise HTTPException(status_code=404, detail="Tracking has not been started for this camera")
    frame = session.latest_frame(heatmap=heatmap)
    if frame is None:
        raise HTTPException(status_code=503, detail="No frame available yet")
    return Response(content=frame, media_type="image/jpeg")
