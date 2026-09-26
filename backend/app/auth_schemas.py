"""Request/response models for authentication, organizations, locations and members."""
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional
from zoneinfo import available_timezones

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.auth import ROLES

MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 128


class RoleName(str, Enum):
    owner = "owner"
    admin = "admin"
    member = "member"


assert {r.value for r in RoleName} == set(ROLES)  # keep the API's roles and app.auth's in sync


def _validate_password(value: str) -> str:
    if not (MIN_PASSWORD_LENGTH <= len(value) <= MAX_PASSWORD_LENGTH):
        raise ValueError(f"Password must be {MIN_PASSWORD_LENGTH}-{MAX_PASSWORD_LENGTH} characters")
    return value


def _validate_timezone(value: str) -> str:
    # Phase 17: previously unvalidated - a bogus value stored fine (String(64) easily
    # holds e.g. "asdf") and only surfaced as a raw Postgres error later, at analytics
    # query time (`timezone(tz, ts)` with an invalid IANA name). Catching it here instead
    # gives a clean 422 at the point a location's timezone is actually set.
    if value not in available_timezones():
        raise ValueError(f"'{value}' is not a recognized IANA time zone name")
    return value


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str = Field(min_length=1, max_length=200)
    organization_name: str = Field(min_length=1, max_length=200)

    _validate_password = field_validator("password")(_validate_password)


class LoginRequest(BaseModel):
    email: EmailStr
    # Phase 17: capped (but not min-length-checked, unlike registration) - a real account's
    # password is always 10-128 chars already, so nothing legitimate is rejected, but an
    # attacker sending a huge string no longer forces a full-length Argon2 verify over it
    # on every attempt.
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)


class RefreshRequest(BaseModel):
    # Phase 17: generate_refresh_token() (app/security.py) always produces a 43-character
    # value - generous headroom, not a tight fit, since this only needs to reject grossly
    # oversized input before it reaches hash_refresh_token.
    refresh_token: str = Field(max_length=200)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    _validate_password = field_validator("new_password")(_validate_password)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str
    created_at: datetime


class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    created_at: datetime


class OrganizationMembershipRead(BaseModel):
    """One organization the current user belongs to, with their role in it — the shape
    `GET /auth/me` and `GET /organizations` list, so the desktop app's organization
    switcher doesn't need a second request per organization."""

    organization: OrganizationRead
    role: RoleName


class MeRead(BaseModel):
    user: UserRead
    organizations: list[OrganizationMembershipRead]


class TokenPairRead(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds, so the client knows when to refresh without decoding the JWT
    user: UserRead
    organizations: list[OrganizationMembershipRead]


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class OrganizationUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class LocationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    timezone: str = "UTC"

    _validate_timezone = field_validator("timezone")(_validate_timezone)


class LocationUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    timezone: Optional[str] = None

    @field_validator("timezone")
    @classmethod
    def _validate_timezone_if_given(cls, value: Optional[str]) -> Optional[str]:
        return _validate_timezone(value) if value is not None else None


class LocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    timezone: str
    created_at: datetime
    camera_count: int = 0


class MemberAddRequest(BaseModel):
    """Adds an *existing* account by email — there is no invitation email to send yet
    (Phase 10 has no email service), so the person must already have registered."""

    email: EmailStr
    role: RoleName = RoleName.member


class MemberRoleUpdate(BaseModel):
    role: RoleName


class MemberRead(BaseModel):
    user_id: uuid.UUID
    email: str
    name: str
    role: RoleName
    created_at: datetime
