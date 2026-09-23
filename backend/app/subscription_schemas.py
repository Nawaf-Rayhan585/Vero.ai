"""Request/response models for the subscription/licensing architecture (Phase 11)."""
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, computed_field

from app.auth import is_subscription_active


class SubscriptionStatus(str, Enum):
    trialing = "trialing"
    active = "active"
    expired = "expired"
    canceled = "canceled"


class PlanType(str, Enum):
    own_hardware = "own_hardware"
    vero_cloud = "vero_cloud"


class SubscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    status: SubscriptionStatus
    plan_type: Optional[PlanType]
    trial_started_at: datetime
    trial_ends_at: datetime
    max_cameras: Optional[int]
    activated_at: Optional[datetime]

    @computed_field
    @property
    def is_active(self) -> bool:
        # Same logic app/auth.py's require_active_configurator enforces (is_subscription_
        # active), so the frontend never has to re-derive the trial math itself.
        return is_subscription_active(self.status.value, self.trial_ends_at)


class SubscriptionUpdate(BaseModel):
    """Owner-only manual override (routers/subscription.py) — a stand-in for real billing
    until Phase 15 ships PayPal. Every field is optional; only what's provided changes."""

    status: Optional[SubscriptionStatus] = None
    plan_type: Optional[PlanType] = None
    trial_ends_at: Optional[datetime] = None
