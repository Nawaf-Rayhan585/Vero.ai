import uuid
from datetime import datetime, timezone

import cv2
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import camera_testing
from app.crypto import decrypt_password, encrypt_password
from app.database import get_db
from app.models import Camera
from app.schemas import CameraCreate, CameraRead, CameraUpdate, camera_to_read

router = APIRouter(prefix="/cameras", tags=["cameras"])


def _get_camera_or_404(db: Session, camera_id: str) -> Camera:
    try:
        parsed_id = uuid.UUID(camera_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Camera not found")
    camera = db.get(Camera, parsed_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    return camera


def _decrypted_credentials(camera: Camera) -> tuple[str | None, str | None]:
    password = decrypt_password(camera.encrypted_password) if camera.encrypted_password else None
    return camera.username, password


@router.post("", response_model=CameraRead)
def create_camera(request: CameraCreate, db: Session = Depends(get_db)):
    camera = Camera(
        name=request.name,
        rtsp_url=request.rtsp_url,
        username=request.username,
        encrypted_password=encrypt_password(request.password) if request.password else None,
        location_label=request.location_label,
        notes=request.notes,
        connection_status="unknown",
    )
    db.add(camera)
    db.commit()
    return camera_to_read(camera)


@router.get("", response_model=list[CameraRead])
def list_cameras(db: Session = Depends(get_db)):
    cameras = db.scalars(select(Camera).order_by(Camera.created_at)).all()
    return [camera_to_read(c) for c in cameras]


@router.get("/{camera_id}", response_model=CameraRead)
def get_camera(camera_id: str, db: Session = Depends(get_db)):
    return camera_to_read(_get_camera_or_404(db, camera_id))


@router.patch("/{camera_id}", response_model=CameraRead)
def update_camera(camera_id: str, request: CameraUpdate, db: Session = Depends(get_db)):
    camera = _get_camera_or_404(db, camera_id)
    updates = request.model_dump(exclude_unset=True)

    if "password" in updates:
        password = updates.pop("password")
        camera.encrypted_password = encrypt_password(password) if password else None
    for field, value in updates.items():
        setattr(camera, field, value)

    db.commit()
    return camera_to_read(camera)


@router.delete("/{camera_id}", status_code=204)
def delete_camera(camera_id: str, db: Session = Depends(get_db)):
    camera = _get_camera_or_404(db, camera_id)
    db.delete(camera)
    db.commit()
    return Response(status_code=204)


@router.post("/{camera_id}/test-connection", response_model=CameraRead)
def test_camera_connection(camera_id: str, db: Session = Depends(get_db)):
    camera = _get_camera_or_404(db, camera_id)
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


@router.get("/{camera_id}/snapshot")
def get_camera_snapshot(camera_id: str, db: Session = Depends(get_db)):
    camera = _get_camera_or_404(db, camera_id)
    username, password = _decrypted_credentials(camera)
    result = camera_testing.grab_snapshot(camera.rtsp_url, username, password)

    if result.frame is None:
        raise HTTPException(status_code=503, detail=result.error or "Camera unavailable")

    ok, encoded = cv2.imencode(".jpg", result.frame)
    if not ok:
        raise HTTPException(status_code=503, detail="Failed to encode snapshot")
    return Response(content=encoded.tobytes(), media_type="image/jpeg")
