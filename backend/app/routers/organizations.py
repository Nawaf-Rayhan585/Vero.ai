import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import ADMIN, OWNER, get_current_user
from app.auth_schemas import (
    OrganizationCreate,
    OrganizationMembershipRead,
    OrganizationRead,
    OrganizationUpdate,
)
from app.database import get_db
from app.models import Location, Membership, Organization, User

router = APIRouter(prefix="/organizations", tags=["organizations"])


def _memberships_read(db: Session, user: User) -> list[OrganizationMembershipRead]:
    rows = db.execute(
        select(Membership, Organization).join(Organization).where(Membership.user_id == user.id)
    ).all()
    return [
        OrganizationMembershipRead(organization=OrganizationRead.model_validate(org), role=membership.role)
        for membership, org in rows
    ]


def _membership_or_404(db: Session, user_id: uuid.UUID, organization_id: str) -> Membership:
    try:
        parsed_id = uuid.UUID(organization_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Organization not found")
    membership = db.scalar(
        select(Membership).where(Membership.user_id == user_id, Membership.organization_id == parsed_id)
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return membership


@router.get("", response_model=list[OrganizationMembershipRead])
def list_my_organizations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _memberships_read(db, user)


@router.post("", response_model=OrganizationMembershipRead)
def create_organization(
    request: OrganizationCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """A user can belong to (and create) several organizations. The creator becomes its
    Owner, with a default location so cameras can be added right away."""
    organization = Organization(name=request.name)
    db.add(organization)
    db.flush()
    db.add(Membership(user_id=user.id, organization_id=organization.id, role=OWNER))
    db.add(Location(organization_id=organization.id, name="Main location"))
    db.commit()
    return OrganizationMembershipRead(organization=OrganizationRead.model_validate(organization), role=OWNER)


@router.patch("/{organization_id}", response_model=OrganizationRead)
def rename_organization(
    organization_id: str,
    request: OrganizationUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    membership = _membership_or_404(db, user.id, organization_id)
    if membership.role not in (ADMIN, OWNER):
        raise HTTPException(status_code=403, detail="You do not have permission to do this")
    organization = db.get(Organization, membership.organization_id)
    organization.name = request.name
    db.commit()
    return organization
