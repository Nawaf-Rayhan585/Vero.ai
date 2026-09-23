"""Authentication and organization-scoping dependencies, plus the one-time adoption of
pre-Phase-10 data.

Every protected route depends on `get_current_user` (who you are) and, where it touches
organization-scoped data, `get_org_context` (which organization you're acting as — chosen
by the `X-Organization-Id` header, defaulting to your only membership if you have exactly
one). A user who is not a member of the requested organization gets a 404, not a 403: the
response never confirms the organization exists.

Roles: **member** can read (live view, events, analytics, lists); **admin**/**owner** can
configure (cameras, lines, zones, locations, modules, tracking, members). Only an owner can
grant the owner role, and the last owner of an organization can't be removed or demoted —
enforced in routers/members.py using `is_last_owner` below.
"""
import uuid
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Camera, Job, Location, Membership, Organization, User
from app.security import TokenError, decode_access_token

MEMBER = "member"
ADMIN = "admin"
OWNER = "owner"
ROLES = (MEMBER, ADMIN, OWNER)
CONFIGURING_ROLES = (ADMIN, OWNER)

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        user_id = decode_access_token(credentials.credentials, get_settings().auth_secret_key)
    except TokenError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user


@dataclass
class OrgContext:
    organization: Organization
    membership: Membership

    @property
    def role(self) -> str:
        return self.membership.role


def get_org_context(
    x_organization_id: Optional[str] = Header(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrgContext:
    memberships = db.scalars(select(Membership).where(Membership.user_id == user.id)).all()

    if x_organization_id is not None:
        try:
            org_id = uuid.UUID(x_organization_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="Organization not found")
        membership = next((m for m in memberships if m.organization_id == org_id), None)
        if membership is None:
            # Never distinguishes "doesn't exist" from "exists but you're not in it".
            raise HTTPException(status_code=404, detail="Organization not found")
    elif len(memberships) == 1:
        membership = memberships[0]
    elif len(memberships) == 0:
        raise HTTPException(status_code=403, detail="You do not belong to any organization")
    else:
        raise HTTPException(
            status_code=400, detail="Specify which organization with the X-Organization-Id header"
        )

    organization = db.get(Organization, membership.organization_id)
    return OrgContext(organization=organization, membership=membership)


def require_role(*roles: str):
    """`Depends(require_role(ADMIN, OWNER))` — 403s if the caller's role in the current
    organization isn't one of `roles`. Read-only routes take no dependency at all: every
    member can read."""

    def check(ctx: OrgContext = Depends(get_org_context)) -> OrgContext:
        if ctx.role not in roles:
            raise HTTPException(status_code=403, detail="You do not have permission to do this")
        return ctx

    return check


require_configurator = require_role(*CONFIGURING_ROLES)


def is_last_owner(db: Session, organization_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    owner_ids = db.scalars(
        select(Membership.user_id).where(Membership.organization_id == organization_id, Membership.role == OWNER)
    ).all()
    return owner_ids == [user_id]


DEFAULT_LOCATION_NAME = "Main location"


def adopt_orphans(db: Session, organization_id: uuid.UUID) -> None:
    """Run once, right after the very first user registers (routers/auth.py checks the
    users table was empty first). Cameras and jobs created before Phase 10 have no
    organization; rather than orphan or delete them, they're adopted into the first
    account — one Location per distinct old `location_label` (or a single default one)."""
    cameras = db.scalars(select(Camera).where(Camera.location_id.is_(None))).all()
    locations_by_label: dict[Optional[str], Location] = {}

    def location_for(label: Optional[str]) -> Location:
        key = label or None
        if key not in locations_by_label:
            name = key or DEFAULT_LOCATION_NAME
            location = db.scalar(
                select(Location).where(Location.organization_id == organization_id, Location.name == name)
            )
            if location is None:
                location = Location(organization_id=organization_id, name=name)
                db.add(location)
                db.flush()
            locations_by_label[key] = location
        return locations_by_label[key]

    for camera in cameras:
        camera.location_id = location_for(camera.location_label).id

    db.execute(
        Job.__table__.update().where(Job.organization_id.is_(None)).values(organization_id=organization_id)
    )
