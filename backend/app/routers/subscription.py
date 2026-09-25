from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import paypal_client
from app.auth import OWNER, OrgContext, get_or_create_subscription, get_org_context, require_role
from app.config import get_settings
from app.database import get_db
from app.models import Subscription
from app.subscription_schemas import PayPalCheckoutRead, SubscriptionRead, SubscriptionUpdate

router = APIRouter(prefix="/subscription", tags=["subscription"])

# PayPal's own subscription statuses (GET /v1/billing/subscriptions/{id}, and the
# matching webhook event types) mapped onto this project's four-value status column.
# APPROVAL_PENDING/APPROVED intentionally map to nothing — the local subscription stays
# whatever it already was (still trialing, most likely) until the buyer actually
# completes approval and PayPal reports ACTIVE.
_PAYPAL_STATUS_TO_LOCAL = {
    "ACTIVE": "active",
    "SUSPENDED": "expired",  # payment retries exhausted, but not explicitly canceled
    "CANCELLED": "canceled",
    "EXPIRED": "expired",
}
_PAYPAL_EVENT_TO_LOCAL_STATUS = {
    "BILLING.SUBSCRIPTION.ACTIVATED": "active",
    "BILLING.SUBSCRIPTION.CANCELLED": "canceled",
    "BILLING.SUBSCRIPTION.EXPIRED": "expired",
    "BILLING.SUBSCRIPTION.SUSPENDED": "expired",
}


def _apply_local_status(sub: Subscription, new_status: str) -> None:
    """Shared by /sync and the webhook handler: stamps activated_at/canceled_at the same
    way the manual override does, but leaves activated_by_user_id None — no admin acted,
    PayPal did."""
    sub.status = new_status
    if new_status == "active" and sub.activated_at is None:
        sub.activated_at = datetime.now(timezone.utc)
    if new_status == "canceled" and sub.canceled_at is None:
        sub.canceled_at = datetime.now(timezone.utc)


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
    expired trial, or "expired"/"canceled") and/or extend `trial_ends_at`. An
    admin/support fallback that coexists with real PayPal billing (Phase 15,
    `/subscription/paypal/*` below), not replaced by it — deliberately *not* gated by
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


@router.post("/paypal/checkout", response_model=PayPalCheckoutRead)
def start_paypal_checkout(ctx: OrgContext = Depends(require_role(OWNER)), db: Session = Depends(get_db)):
    """Creates a real PayPal subscription against the Own Hardware plan and returns its
    approve URL — the desktop app opens this in the system browser (Phase 15's
    system-browser-handoff design; see docs/ROADMAP.md). Only for organizations that have
    already chosen the Own Hardware plan; Vero Cloud billing doesn't exist yet."""
    settings = get_settings()
    if not settings.paypal_return_base_url:
        raise HTTPException(status_code=503, detail="PayPal billing isn't configured on this backend")

    sub = ctx.organization.subscription or get_or_create_subscription(db, ctx.organization.id)
    if sub.plan_type != "own_hardware":
        raise HTTPException(
            status_code=400,
            detail="Choose the Own Hardware plan before subscribing — PayPal billing isn't available for Vero Cloud yet.",
        )

    response = paypal_client.create_subscription(
        organization_id=str(ctx.organization.id),
        return_url=f"{settings.paypal_return_base_url}/subscription/paypal/return",
        cancel_url=f"{settings.paypal_return_base_url}/subscription/paypal/cancel-return",
    )
    approve_url = next((link["href"] for link in response["links"] if link["rel"] == "approve"), None)
    if approve_url is None:
        raise HTTPException(status_code=502, detail="PayPal did not return an approval link")

    sub.paypal_subscription_id = response["id"]
    sub.paypal_plan_id = response.get("plan_id") or settings.paypal_own_hardware_plan_id
    db.commit()
    return PayPalCheckoutRead(approve_url=approve_url)


@router.post("/paypal/sync", response_model=SubscriptionRead)
def sync_paypal_subscription(ctx: OrgContext = Depends(require_role(OWNER)), db: Session = Depends(get_db)):
    """Re-checks the real PayPal subscription's status and updates the local row — the
    desktop app calls this after the user returns from approving in the system browser
    (this backend has no way to know that happened otherwise: it's an outbound call to
    PayPal, not an inbound webhook, so it needs no public reachability to work)."""
    sub = ctx.organization.subscription or get_or_create_subscription(db, ctx.organization.id)
    if sub.paypal_subscription_id is None:
        raise HTTPException(status_code=404, detail="This organization has no PayPal subscription to check")

    response = paypal_client.get_subscription(sub.paypal_subscription_id)
    new_status = _PAYPAL_STATUS_TO_LOCAL.get(response["status"])
    if new_status is not None:
        _apply_local_status(sub, new_status)
        db.commit()
    return SubscriptionRead.model_validate(sub)


@router.post("/paypal/cancel", response_model=SubscriptionRead)
def cancel_paypal_subscription(ctx: OrgContext = Depends(require_role(OWNER)), db: Session = Depends(get_db)):
    """Cancels the real PayPal subscription and reflects that locally immediately —
    PayPal's own default behavior has no grace period, and this project tracks none
    either, so canceling here means canceled now, not "at period end"."""
    sub = ctx.organization.subscription or get_or_create_subscription(db, ctx.organization.id)
    if sub.paypal_subscription_id is None:
        raise HTTPException(status_code=404, detail="This organization has no PayPal subscription to cancel")

    paypal_client.cancel_subscription(sub.paypal_subscription_id)
    _apply_local_status(sub, "canceled")
    db.commit()
    return SubscriptionRead.model_validate(sub)


_RETURN_PAGE = """<!DOCTYPE html><html><head><title>Vero.ai</title></head>
<body style="font-family: sans-serif; text-align: center; padding: 4rem;">
<h1>{heading}</h1><p>{message} You can close this tab and return to Vero.ai.</p>
</body></html>"""


@router.get("/paypal/return", response_class=HTMLResponse, include_in_schema=False)
def paypal_return_page():
    """PayPal redirects the buyer's browser here after approval. Deliberately a static
    page with no database write: this request carries no proof of who's asking (no JWT —
    it's a plain browser GET), so it never touches subscription state. The desktop app's
    own authenticated /paypal/sync call (above) is what actually updates anything, once
    the user returns to the app themselves."""
    return HTMLResponse(_RETURN_PAGE.format(heading="Subscription approved", message="Thanks!"))


@router.get("/paypal/cancel-return", response_class=HTMLResponse, include_in_schema=False)
def paypal_cancel_return_page():
    return HTMLResponse(_RETURN_PAGE.format(heading="Checkout canceled", message="Nothing was charged."))


@router.post("/paypal/webhook", include_in_schema=False)
async def paypal_webhook(request: Request, db: Session = Depends(get_db)):
    """PayPal's server-to-server notification of subscription lifecycle events. Real,
    production-correct code — verified via PayPal's own verify-webhook-signature endpoint
    (app/paypal_client.py) rather than reimplementing RSA-SHA256 locally — but this dev
    environment has no public HTTPS endpoint for PayPal's real servers to reach, so this
    handler is untestable live here; /paypal/sync above is this phase's actual verified
    mechanism. Always returns 200 once the signature is valid (even for an event type or
    subscription id this backend doesn't act on) so PayPal doesn't retry pointlessly."""
    parsed_body = await request.json()
    if not paypal_client.verify_webhook_signature(dict(request.headers), parsed_body):
        raise HTTPException(status_code=400, detail="Could not verify this webhook's signature")

    new_status = _PAYPAL_EVENT_TO_LOCAL_STATUS.get(parsed_body.get("event_type"))
    paypal_subscription_id = parsed_body.get("resource", {}).get("id")
    if new_status is not None and paypal_subscription_id is not None:
        sub = db.scalar(select(Subscription).where(Subscription.paypal_subscription_id == paypal_subscription_id))
        if sub is not None:
            _apply_local_status(sub, new_status)
            db.commit()
    return {"status": "ok"}
