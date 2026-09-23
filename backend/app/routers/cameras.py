import uuid
from datetime import datetime, timezone

import cv2
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import camera_testing
from app.auth import OrgContext, get_org_context, require_active_configurator, require_configurator
from app.cloud_routing import is_cloud_organization, proxy_to_cloud_engine, relay_bytes, relay_json
from app.crypto import decrypt_password, encrypt_password
from app.database import get_db
from app.models import Camera, Location
from app.routers.locations import _get_location_or_404
from app.schemas import CameraCreate, CameraRead, CameraUpdate, camera_to_read

router = APIRouter(prefix="/cameras", tags=["cameras"])


def _get_camera_or_404(db: Session, ctx: OrgContext, camera_id: str) -> Camera:
    try:
        parsed_id = uuid.UUID(camera_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Camera not found")
    camera = db.scalar(
        select(Camera).join(Location).where(Camera.id == parsed_id, Location.organization_id == ctx.organization.id)
    )
    if camera is None:
        # Never distinguishes "does not exist" from "belongs to another organization".
        raise HTTPException(status_code=404, detail="Camera not found")
    return camera


def _camera_ids_for_org(db: Session, ctx: OrgContext) -> list[uuid.UUID]:
    """Every camera id in the caller's organization — the scoping list events/analytics
    queries use when no specific camera was asked for. An organization with no cameras
    correctly yields an empty list, not "unscoped"."""
    return list(
        db.scalars(select(Camera.id).join(Location).where(Location.organization_id == ctx.organization.id)).all()
    )


def _decrypted_credentials(camera: Camera) -> tuple[str | None, str | None]:
    password = decrypt_password(camera.encrypted_password) if camera.encrypted_password else None
    return camera.username, password


def _default_location(db: Session, ctx: OrgContext) -> Location:
    location = db.scalar(
        select(Location).where(Location.organization_id == ctx.organization.id).order_by(Location.created_at)
    )
    if location is None:
        raise HTTPException(
            status_code=422, detail="This organization has no locations; create one first, or specify location_id"
        )
    return location


def _check_camera_limit(db: Session, ctx: OrgContext) -> None:
    """The entitlement mechanism Phase 11 builds (docs/ROADMAP.md): `max_cameras` is None
    (unlimited) for every real organization today, since Phase 14 hasn't decided real
    numbers yet — this only actually blocks anything in a test that sets it directly."""
    sub = ctx.organization.subscription
    if sub is None or sub.max_cameras is None:
        return
    count = db.scalar(
        select(func.count()).select_from(Camera).join(Location).where(Location.organization_id == ctx.organization.id)
    )
    if count >= sub.max_cameras:
        raise HTTPException(
            status_code=402, detail=f"Your plan allows up to {sub.max_cameras} camera(s). Upgrade to add more."
        )


@router.post("", response_model=CameraRead)
def create_camera(
    request: CameraCreate, ctx: OrgContext = Depends(require_active_configurator), db: Session = Depends(get_db)
):
    _check_camera_limit(db, ctx)
    location = (
        _get_location_or_404(db, ctx, str(request.location_id))
        if request.location_id is not None
        else _default_location(db, ctx)
    )
    camera = Camera(
        name=request.name,
        rtsp_url=request.rtsp_url,
        username=request.username,
        encrypted_password=encrypt_password(request.password) if request.password else None,
        location_id=location.id,
        notes=request.notes,
        connection_status="unknown",
        enabled_modules=request.enabled_modules,
    )
    db.add(camera)
    db.commit()
    return camera_to_read(camera)


@router.get("", response_model=list[CameraRead])
def list_cameras(ctx: OrgContext = Depends(get_org_context), db: Session = Depends(get_db)):
    cameras = db.scalars(
        select(Camera).join(Location).where(Location.organization_id == ctx.organization.id).order_by(Camera.created_at)
    ).all()
    return [camera_to_read(c) for c in cameras]


@router.get("/{camera_id}", response_model=CameraRead)
def get_camera(camera_id: str, ctx: OrgContext = Depends(get_org_context), db: Session = Depends(get_db)):
    return camera_to_read(_get_camera_or_404(db, ctx, camera_id))


@router.patch("/{camera_id}", response_model=CameraRead)
def update_camera(
    camera_id: str,
    request: CameraUpdate,
    ctx: OrgContext = Depends(require_active_configurator),
    db: Session = Depends(get_db),
):
    camera = _get_camera_or_404(db, ctx, camera_id)
    updates = request.model_dump(exclude_unset=True)
    # An explicit null means "leave it as is", not "clear it" — the columns are NOT NULL.
    if updates.get("enabled_modules", ...) is None:
        updates.pop("enabled_modules", None)
    if "location_id" in updates:
        if updates["location_id"] is None:
            updates.pop("location_id")
        else:
            updates["location_id"] = _get_location_or_404(db, ctx, str(updates["location_id"])).id

    if "password" in updates:
        password = updates.pop("password")
        camera.encrypted_password = encrypt_password(password) if password else None
    for field, value in updates.items():
        setattr(camera, field, value)

    db.commit()
    if "location_id" in updates:
        # expire_on_commit=False (app/database.py) means camera.location would otherwise
        # keep pointing at the *old* location object loaded before this change.
        db.expire(camera, ["location"])
    return camera_to_read(camera)


@router.delete("/{camera_id}", status_code=204)
def delete_camera(camera_id: str, ctx: OrgContext = Depends(require_configurator), db: Session = Depends(get_db)):
    camera = _get_camera_or_404(db, ctx, camera_id)
    db.delete(camera)
    db.commit()
    return Response(status_code=204)


@router.post("/{camera_id}/test-connection", response_model=CameraRead)
def test_camera_connection(
    camera_id: str, ctx: OrgContext = Depends(require_configurator), db: Session = Depends(get_db)
):
    camera = _get_camera_or_404(db, ctx, camera_id)
    if is_cloud_organization(ctx):
        response = proxy_to_cloud_engine("POST", f"/cameras/{camera.id}/test-connection")
        return relay_json(response)

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
def get_camera_snapshot(camera_id: str, ctx: OrgContext = Depends(get_org_context), db: Session = Depends(get_db)):
    camera = _get_camera_or_404(db, ctx, camera_id)
    if is_cloud_organization(ctx):
        response = proxy_to_cloud_engine("GET", f"/cameras/{camera.id}/snapshot")
        return relay_bytes(response)

    username, password = _decrypted_credentials(camera)
    result = camera_testing.grab_snapshot(camera.rtsp_url, username, password)

    if result.frame is None:
        raise HTTPException(status_code=503, detail=result.error or "Camera unavailable")

    ok, encoded = cv2.imencode(".jpg", result.frame)
    if not ok:
        raise HTTPException(status_code=503, detail="Failed to encode snapshot")
    return Response(content=encoded.tobytes(), media_type="image/jpeg")
