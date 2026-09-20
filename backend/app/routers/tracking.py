import dataclasses

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.routers.cameras import _decrypted_credentials, _get_camera_or_404
from app.schemas import TrackingStatusRead
from app.tracking import TrackingStatusSnapshot, tracking_manager

router = APIRouter(prefix="/cameras", tags=["tracking"])

_STOPPED_SNAPSHOT = TrackingStatusRead(status="stopped", frame_count=0, active_track_ids=[])


def _to_status_read(snapshot: TrackingStatusSnapshot) -> TrackingStatusRead:
    return TrackingStatusRead(**dataclasses.asdict(snapshot))


@router.post("/{camera_id}/tracking/start", response_model=TrackingStatusRead)
def start_tracking(camera_id: str, db: Session = Depends(get_db)):
    camera = _get_camera_or_404(db, camera_id)
    username, password = _decrypted_credentials(camera)
    session = tracking_manager.start(camera.id, camera.rtsp_url, username, password)
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
def get_latest_tracking_frame(camera_id: str, db: Session = Depends(get_db)):
    camera = _get_camera_or_404(db, camera_id)
    session = tracking_manager.get(camera.id)
    if session is None:
        raise HTTPException(status_code=404, detail="Tracking has not been started for this camera")
    frame = session.latest_frame()
    if frame is None:
        raise HTTPException(status_code=503, detail="No frame available yet")
    return Response(content=frame, media_type="image/jpeg")
