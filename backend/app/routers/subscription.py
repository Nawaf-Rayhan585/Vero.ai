from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import OWNER, OrgContext, get_or_create_subscription, get_org_context, require_role
from app.database import get_db
from app.subscription_schemas import SubscriptionRead, SubscriptionUpdate

router = APIRouter(prefix="/subscription", tags=["subscription"])


@router.get("", response_model=SubscriptionRead)
def get_subscription(ctx: OrgContext = Depends(get_org_context), db: Session = Depends(get_db)):
    """Any member can read their organization's subscription — the trial countdown and
    plan matter to everyone using the app, not just whoever configures it."""
    sub = ctx.organization.subscription or get_or_create_subscription(db, ctx.organization.id)
    return SubscriptionRead.model_validate(sub)


@router.patch("", response_model=SubscriptionRead)
def update_subscription(
    request: SubscriptionUpdate,
    ctx: OrgContext = Depends(require_role(OWNER)),
    db: Session = Depends(get_db),
):
    """Owner-only manual override: set status directly (e.g. "active" to unblock an
    expired trial, or "expired"/"canceled") and/or extend `trial_ends_at`. A stand-in for
    real billing until Phase 15 ships PayPal — deliberately *not* gated by
    require_active_configurator, since you must be able to activate an already-expired
    organization."""
    sub = ctx.organization.subscription or get_or_create_subscription(db, ctx.organization.id)
    updates = request.model_dump(exclude_unset=True)

    if "status" in updates:
        sub.status = updates["status"].value
        if sub.status == "active":
            sub.activated_at = datetime.now(timezone.utc)
            sub.activated_by_user_id = ctx.membership.user_id
    if "plan_type" in updates:
        plan_type = updates["plan_type"]
        sub.plan_type = plan_type.value if plan_type is not None else None
    if "trial_ends_at" in updates:
        sub.trial_ends_at = updates["trial_ends_at"]

    db.commit()
    return SubscriptionRead.model_validate(sub)
