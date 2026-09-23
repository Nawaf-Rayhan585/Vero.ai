import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import OrgContext, get_org_context, require_configurator
from app.database import get_db
from app.models import Camera, Location, Zone
from app.routers.cameras import _get_camera_or_404
from app.schemas import ZoneCreate, ZoneRead

router = APIRouter(tags=["zones"])


def _get_zone_or_404(db: Session, ctx: OrgContext, zone_id: str) -> Zone:
    try:
        parsed_id = uuid.UUID(zone_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Zone not found")
    # A zone's organization is zone -> camera -> location -> organization, the same chain
    # _get_camera_or_404 checks.
    zone = db.scalar(
        select(Zone)
        .join(Camera, Zone.camera_id == Camera.id)
        .join(Location, Camera.location_id == Location.id)
        .where(Zone.id == parsed_id, Location.organization_id == ctx.organization.id)
    )
    if zone is None:
        raise HTTPException(status_code=404, detail="Zone not found")
    return zone


@router.post("/cameras/{camera_id}/zones", response_model=ZoneRead)
def create_zone(
    camera_id: str, request: ZoneCreate, ctx: OrgContext = Depends(require_configurator), db: Session = Depends(get_db)
):
    camera = _get_camera_or_404(db, ctx, camera_id)
    zone = Zone(
        camera_id=camera.id,
        name=request.name,
        points=[{"x": p.x, "y": p.y} for p in request.points],
    )
    db.add(zone)
    db.commit()
    return zone


@router.get("/cameras/{camera_id}/zones", response_model=list[ZoneRead])
def list_zones(camera_id: str, ctx: OrgContext = Depends(get_org_context), db: Session = Depends(get_db)):
    camera = _get_camera_or_404(db, ctx, camera_id)
    return db.scalars(select(Zone).where(Zone.camera_id == camera.id).order_by(Zone.created_at)).all()


@router.delete("/zones/{zone_id}", status_code=204)
def delete_zone(zone_id: str, ctx: OrgContext = Depends(require_configurator), db: Session = Depends(get_db)):
    zone = _get_zone_or_404(db, ctx, zone_id)
    db.delete(zone)
    db.commit()
    return Response(status_code=204)
