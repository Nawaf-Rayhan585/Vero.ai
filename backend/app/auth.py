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

Phase 11 adds a second gate on top of the role check, for the subset of configure actions
that *grow* usage (create/edit a camera, line, zone, location or member; start tracking):
`require_active_configurator` additionally 402s once an organization's trial has ended
with no active subscription. Actions that *shrink* usage (delete anything, stop tracking,
remove/leave a member) keep using plain `require_configurator` and are never blocked by
billing status — see routers/subscription.py for the (Owner-only, manual-override-for-now)
way a subscription becomes active before Phase 15 ships real billing.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Camera, Job, Location, Membership, Organization, Subscription, User
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


def is_subscription_active(status: str, trial_ends_at: datetime) -> bool:
    """True if the organization can currently create or grow usage: an active
    subscription, or a trial that hasn't reached its end date yet. Anything else
    ("expired", "canceled", or a trial past `trial_ends_at`) is not. Takes plain values,
    not a `Subscription` row, so `SubscriptionRead`'s `is_active` computed field
    (app/subscription_schemas.py) can share this exact logic instead of reimplementing
    it against its own (Pydantic, not ORM) `status`/`trial_ends_at`."""
    if status == "active":
        return True
    if status == "trialing":
        return trial_ends_at > datetime.now(timezone.utc)
    return False


def new_trial_subscription(organization_id: uuid.UUID) -> Subscription:
    """A fresh, unsaved trial Subscription for a just-created organization. Deliberately
    doesn't add/commit itself — routers/auth.py's `register` and
    routers/organizations.py's `create_organization` add it alongside the organization's
    other new rows (membership, default location) so the whole registration/creation
    commits atomically, same as before this function existed."""
    now = datetime.now(timezone.utc)
    return Subscription(
        organization_id=organization_id,
        status="trialing",
        trial_started_at=now,
        trial_ends_at=now + timedelta(days=get_settings().trial_days),
    )


def get_or_create_subscription(db: Session, organization_id: uuid.UUID) -> Subscription:
    """Every organization gets a subscription the moment it's created, via
    `new_trial_subscription` above, and the Phase 11 migration backfills every
    organization that predates it — so this should always find a row. Self-heals (and
    commits immediately, since there's no larger transaction to stay atomic with here)
    rather than ever hard-failing if one is somehow still missing."""
    sub = db.scalar(select(Subscription).where(Subscription.organization_id == organization_id))
    if sub is None:
        sub = new_trial_subscription(organization_id)
        db.add(sub)
        db.commit()
    return sub


def require_active_configurator(
    ctx: OrgContext = Depends(require_configurator), db: Session = Depends(get_db)
) -> OrgContext:
    """Like `require_configurator` (same role check), plus: refuses to let an expired
    trial with no active subscription create or grow usage. Deliberately a separate,
    explicitly-opted-into dependency — `require_configurator` itself is unchanged, so
    every "shrink" action (delete, stop tracking, remove a member) keeps working
    regardless of billing status; see the routers for which endpoints use which."""
    sub = ctx.organization.subscription or get_or_create_subscription(db, ctx.organization.id)
    if not is_subscription_active(sub.status, sub.trial_ends_at):
        raise HTTPException(
            status_code=402,
            detail="Your trial has ended. Upgrade on the Subscription page to keep making changes.",
        )
    return ctx


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
