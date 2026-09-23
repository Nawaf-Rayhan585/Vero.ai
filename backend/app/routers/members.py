import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import CONFIGURING_ROLES, OWNER, OrgContext, get_org_context, is_last_owner, require_configurator
from app.auth_schemas import MemberAddRequest, MemberRead, MemberRoleUpdate
from app.database import get_db
from app.models import Membership, User

router = APIRouter(prefix="/members", tags=["members"])


def _to_read(membership: Membership, user: User) -> MemberRead:
    return MemberRead(
        user_id=user.id, email=user.email, name=user.name, role=membership.role, created_at=membership.created_at
    )


def _require_owner_to_grant(role: str, ctx: OrgContext) -> None:
    if role == OWNER and ctx.role != OWNER:
        raise HTTPException(status_code=403, detail="Only an owner can grant the owner role")


@router.get("", response_model=list[MemberRead])
def list_members(ctx: OrgContext = Depends(get_org_context), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Membership, User)
        .join(User)
        .where(Membership.organization_id == ctx.organization.id)
        .order_by(User.email)
    ).all()
    return [_to_read(m, u) for m, u in rows]


@router.post("", response_model=MemberRead)
def add_member(
    request: MemberAddRequest, ctx: OrgContext = Depends(require_configurator), db: Session = Depends(get_db)
):
    """Adds an existing account by email. There is no invitation email (no email service
    exists yet), so the person must already have registered their own account."""
    _require_owner_to_grant(request.role.value, ctx)
    email = request.email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        raise HTTPException(status_code=404, detail="No account with this email has registered yet")
    if db.scalar(
        select(Membership).where(Membership.user_id == user.id, Membership.organization_id == ctx.organization.id)
    ):
        raise HTTPException(status_code=409, detail="This person is already a member")

    membership = Membership(user_id=user.id, organization_id=ctx.organization.id, role=request.role.value)
    db.add(membership)
    db.commit()
    return _to_read(membership, user)


def _get_membership_or_404(db: Session, ctx: OrgContext, user_id: str) -> Membership:
    try:
        parsed_id = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")
    membership = db.scalar(
        select(Membership).where(Membership.user_id == parsed_id, Membership.organization_id == ctx.organization.id)
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="Member not found")
    return membership


@router.patch("/{user_id}", response_model=MemberRead)
def update_member_role(
    user_id: str,
    request: MemberRoleUpdate,
    ctx: OrgContext = Depends(require_configurator),
    db: Session = Depends(get_db),
):
    membership = _get_membership_or_404(db, ctx, user_id)
    _require_owner_to_grant(request.role.value, ctx)
    if membership.role == OWNER and request.role.value != OWNER and is_last_owner(db, ctx.organization.id, membership.user_id):
        raise HTTPException(status_code=409, detail="An organization must always have at least one owner")

    membership.role = request.role.value
    db.commit()
    return _to_read(membership, db.get(User, membership.user_id))


@router.delete("/{user_id}", status_code=204)
def remove_member(
    user_id: str, ctx: OrgContext = Depends(get_org_context), db: Session = Depends(get_db)
):
    """A member may remove themself (leave); removing someone else needs admin/owner."""
    membership = _get_membership_or_404(db, ctx, user_id)
    is_self = membership.user_id == ctx.membership.user_id
    if not is_self and ctx.role not in CONFIGURING_ROLES:
        raise HTTPException(status_code=403, detail="You do not have permission to do this")
    if membership.role == OWNER and is_last_owner(db, ctx.organization.id, membership.user_id):
        raise HTTPException(status_code=409, detail="An organization must always have at least one owner")

    db.delete(membership)
    db.commit()
    return None
