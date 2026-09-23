"""Request/response models for device entitlement (Phase 12) — see app/models.py's
`Device` for what a "device" actually is here (a name someone typed, not a hardware
fingerprint)."""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class DeviceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    notes: Optional[str] = None


class DeviceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    notes: Optional[str] = None


class DeviceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    notes: Optional[str]
    created_at: datetime
