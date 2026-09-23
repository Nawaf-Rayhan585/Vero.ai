import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import OrgContext, get_org_context, require_active_configurator, require_configurator
from app.database import get_db
from app.device_schemas import DeviceCreate, DeviceRead, DeviceUpdate
from app.models import Device

router = APIRouter(prefix="/devices", tags=["devices"])


def _get_device_or_404(db: Session, ctx: OrgContext, device_id: str) -> Device:
    try:
        parsed_id = uuid.UUID(device_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Device not found")
    device = db.scalar(select(Device).where(Device.id == parsed_id, Device.organization_id == ctx.organization.id))
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


def _check_device_limit(db: Session, ctx: OrgContext) -> None:
    """The entitlement mechanism Phase 12 builds (docs/ROADMAP.md): `max_devices` is None
    (unlimited) for every real organization today, since Phase 14 hasn't decided real
    numbers yet — this only actually blocks anything in a test that sets it directly."""
    sub = ctx.organization.subscription
    if sub is None or sub.max_devices is None:
        return
    count = db.scalar(select(func.count()).select_from(Device).where(Device.organization_id == ctx.organization.id))
    if count >= sub.max_devices:
        raise HTTPException(
            status_code=402, detail=f"Your plan allows up to {sub.max_devices} device(s). Upgrade to add more."
        )


@router.get("", response_model=list[DeviceRead])
def list_devices(ctx: OrgContext = Depends(get_org_context), db: Session = Depends(get_db)):
    """Any member can read the list — it's a record of the organization's hardware, not a
    configuration surface only Admin/Owner need."""
    devices = db.scalars(
        select(Device).where(Device.organization_id == ctx.organization.id).order_by(Device.name)
    ).all()
    return devices


@router.post("", response_model=DeviceRead)
def create_device(
    request: DeviceCreate, ctx: OrgContext = Depends(require_active_configurator), db: Session = Depends(get_db)
):
    _check_device_limit(db, ctx)
    device = Device(organization_id=ctx.organization.id, name=request.name, notes=request.notes)
    db.add(device)
    db.commit()
    return device


@router.patch("/{device_id}", response_model=DeviceRead)
def update_device(
    device_id: str,
    request: DeviceUpdate,
    ctx: OrgContext = Depends(require_active_configurator),
    db: Session = Depends(get_db),
):
    device = _get_device_or_404(db, ctx, device_id)
    updates = request.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(device, field, value)
    db.commit()
    return device


@router.delete("/{device_id}", status_code=204)
def delete_device(device_id: str, ctx: OrgContext = Depends(require_configurator), db: Session = Depends(get_db)):
    device = _get_device_or_404(db, ctx, device_id)
    db.delete(device)
    db.commit()
    return None
