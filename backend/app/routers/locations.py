import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import OrgContext, get_org_context, require_configurator
from app.auth_schemas import LocationCreate, LocationRead, LocationUpdate
from app.database import get_db
from app.models import Camera, Location

router = APIRouter(prefix="/locations", tags=["locations"])


def _get_location_or_404(db: Session, ctx: OrgContext, location_id: str) -> Location:
    try:
        parsed_id = uuid.UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Location not found")
    location = db.scalar(
        select(Location).where(Location.id == parsed_id, Location.organization_id == ctx.organization.id)
    )
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")
    return location


def _with_camera_count(db: Session, locations: list[Location]) -> list[LocationRead]:
    counts = dict(
        db.execute(
            select(Camera.location_id, func.count())
            .where(Camera.location_id.in_([loc.id for loc in locations]))
            .group_by(Camera.location_id)
        ).all()
    )
    return [
        LocationRead.model_validate(loc).model_copy(update={"camera_count": counts.get(loc.id, 0)})
        for loc in locations
    ]


@router.get("", response_model=list[LocationRead])
def list_locations(ctx: OrgContext = Depends(get_org_context), db: Session = Depends(get_db)):
    locations = db.scalars(
        select(Location).where(Location.organization_id == ctx.organization.id).order_by(Location.name)
    ).all()
    return _with_camera_count(db, locations)


@router.post("", response_model=LocationRead)
def create_location(
    request: LocationCreate, ctx: OrgContext = Depends(require_configurator), db: Session = Depends(get_db)
):
    location = Location(organization_id=ctx.organization.id, name=request.name, timezone=request.timezone)
    db.add(location)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A location with this name already exists")
    return _with_camera_count(db, [location])[0]


@router.patch("/{location_id}", response_model=LocationRead)
def update_location(
    location_id: str,
    request: LocationUpdate,
    ctx: OrgContext = Depends(require_configurator),
    db: Session = Depends(get_db),
):
    location = _get_location_or_404(db, ctx, location_id)
    updates = request.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(location, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A location with this name already exists")
    return _with_camera_count(db, [location])[0]


@router.delete("/{location_id}", status_code=204)
def delete_location(
    location_id: str, ctx: OrgContext = Depends(require_configurator), db: Session = Depends(get_db)
):
    location = _get_location_or_404(db, ctx, location_id)
    camera_count = db.scalar(select(func.count()).where(Camera.location_id == location.id))
    if camera_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"This location has {camera_count} camera(s) on it. Move or delete them first.",
        )
    db.delete(location)
    db.commit()
    return None
