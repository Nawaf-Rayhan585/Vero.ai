import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, LargeBinary, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.modules import DEFAULT_MODULES


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Always stored lowercased (app/routers/auth.py normalizes it) so lookups and the
    # unique constraint are case-insensitive without a citext extension.
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    subscription: Mapped[Optional["Subscription"]] = relationship(uselist=False, lazy="joined")


class Membership(Base):
    """A user's role within one organization. A user can belong to several organizations
    (docs/ARCHITECTURE.md: "one user across multiple organizations where appropriate")."""

    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "organization_id", name="uq_membership_user_org"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    # "owner" / "admin" / "member" (app/auth.py). Plain string, not an enum column, so
    # adding a role later is a data migration, not a schema one.
    role: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )


class Location(Base):
    __tablename__ = "locations"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_location_org_name"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    # IANA name, default UTC. Not used yet, but a location — not a camera — is the natural
    # place for "what time zone is this site in", ahead of per-location analytics later.
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", server_default="UTC")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )


class Device(Base):
    """A physical machine an organization says it runs Vero.ai on (Phase 12's device
    entitlement — app/device_schemas.py, routers/devices.py). Deliberately just a record:
    a name someone typed, not a hardware fingerprint, and nothing checks that a request
    actually originates from a registered device. `Subscription.max_devices` is the
    entitlement limit (None = unlimited, and always None today)."""

    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )


class Subscription(Base):
    """One row per organization (app/subscription_schemas.py, routers/subscription.py):
    the trial/subscription state Phase 11 introduces. `status` is "trialing", "active",
    "expired" or "canceled"; a trialing subscription is treated as active only while
    `trial_ends_at` is still in the future (app/auth.py's `is_subscription_active`).
    `plan_type` ("own_hardware" / "vero_cloud") and `max_cameras` exist as the
    architecture for Phase 12-14, but nothing sets them yet — every organization's
    `max_cameras` is still None (unlimited). Phase 14 calculated a real Vero Cloud price
    (docs/PRICING-MODEL.md) but deliberately didn't wire a number in here — entitlement
    *limits* remain undecided for both plans. Phase 15 wires real PayPal billing *status*
    for Own Hardware only (Vero Cloud billing is a separate, deferred phase) — see
    `paypal_subscription_id` below and routers/subscription.py's `/subscription/paypal/*`
    endpoints; the Owner-only manual override from Phase 11 still exists alongside it as
    an admin/support fallback, not replaced by it."""

    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), unique=True
    )
    status: Mapped[str] = mapped_column(String(16), default="trialing", server_default="trialing")
    plan_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    trial_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    trial_ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # The entitlement mechanism (Phase 11's "licensing architecture"): None means
    # unlimited. Enforced by routers/cameras.py's create_camera; still never set on a
    # real organization — Phase 14 priced Vero Cloud (docs/PRICING-MODEL.md) but left
    # wiring a real number here to Phase 15, once there's real billing to enforce it.
    max_cameras: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Same shape, for devices (Phase 12): enforced by routers/devices.py's create_device;
    # never set on any real organization either.
    max_devices: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Set either by the Owner-only manual override (routers/subscription.py) or by a real
    # PayPal activation (Phase 15) — both set activated_at/activated_by_user_id the same
    # way; activated_by_user_id stays None for a PayPal-driven activation (no admin acted).
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Phase 15: real PayPal billing for the Own Hardware plan (app/paypal_client.py,
    # routers/subscription.py's /subscription/paypal/* endpoints). None means this
    # subscription has never had a real PayPal subscription behind it — only the manual
    # override (Phase 11) has ever touched it. Sandbox-only until a later phase goes live.
    paypal_subscription_id: Mapped[Optional[str]] = mapped_column(String(64), unique=True, nullable=True)
    paypal_plan_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    canceled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class RefreshToken(Base):
    """A refresh token's row. The token value itself is never stored — only its SHA-256
    hash (app/security.py) — so reading the database can't hand out a working session.
    `replaced_by` links a used-and-rotated token to the one issued in its place, which is
    what lets reuse of an already-rotated token be detected as theft."""

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("refresh_tokens.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )


class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    rtsp_url: Mapped[str] = mapped_column(Text)
    username: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    encrypted_password: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Legacy free-text location, kept only so the one-time adoption step (app/auth.py's
    # adopt_orphans) can turn pre-Phase-10 cameras' labels into real Location rows. The API
    # no longer reads or writes it — use location_id.
    location_label: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    # Nullable at the database level only so rows created before this column existed keep
    # loading; every camera the API creates or updates always has one. ON DELETE RESTRICT:
    # deleting a location with cameras on it would silently destroy their history, so the
    # location must be emptied (or the cameras moved) first.
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("locations.id", ondelete="RESTRICT"), nullable=True
    )
    location: Mapped[Optional["Location"]] = relationship(lazy="joined")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    connection_status: Mapped[str] = mapped_column(String(16), default="unknown", server_default="unknown")
    last_tested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_fps: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Which AI modules this camera runs (ids from app.modules). Applied when tracking
    # starts, like lines and zones. Cameras created before per-camera selection existed
    # got the server default, i.e. the people-only behavior they always had.
    enabled_modules: Mapped[list] = mapped_column(
        JSONB,
        default=lambda: list(DEFAULT_MODULES),
        server_default=text("""'["people"]'::jsonb"""),
    )


class Line(Base):
    __tablename__ = "lines"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    camera_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cameras.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    # Normalized 0.0-1.0, not pixels: resolution-independent, since the annotated
    # frame's actual size isn't known until a camera is actually opened.
    x1: Mapped[float] = mapped_column(Float)
    y1: Mapped[float] = mapped_column(Float)
    x2: Mapped[float] = mapped_column(Float)
    y2: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )


class Zone(Base):
    __tablename__ = "zones"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    camera_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cameras.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    # A polygon has a variable number of vertices, so a JSONB list of {"x", "y"} rather
    # than a child table. Normalized 0.0-1.0 like Line's coordinates, for the same reason.
    points: Mapped[list] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )


class Event(Base):
    """One structured thing a camera's AI modules observed (see docs/ARCHITECTURE.md,
    "Event schema"). Flat, nullable, indexable columns rather than a JSONB blob: analytics
    group by these fields, and a flat row is what a later cloud sync will want to send.
    Never holds video or images.
    """

    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_camera_time", "camera_id", "occurred_at"),
        Index("ix_events_type_time", "event_type", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Deleting a camera deletes its history, like its lines and zones.
    camera_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cameras.id", ondelete="CASCADE"))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    event_type: Mapped[str] = mapped_column(String(32))
    # "person" / "vehicle" for crossings and zone events; "qr" / "barcode" / "ocr" for reads.
    category: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    direction: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)  # "in" / "out"
    # The line or zone concerned. Deliberately not a foreign key: a line or zone can be
    # deleted later, and the history must survive with the name it had at the time.
    subject_id: Mapped[Optional[uuid.UUID]] = mapped_column(nullable=True)
    subject_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # read text / error message
    detail: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)  # symbology / OCR confidence


class HeatmapSnapshot(Base):
    """Where people stood during one hour, for one camera: a zlib-compressed uint32 grid
    (see app/heatmap.py). One row per camera per UTC hour and grid size, merged on upsert.
    """

    __tablename__ = "heatmap_snapshots"
    __table_args__ = (
        UniqueConstraint("camera_id", "period_start", "grid_width", "grid_height", name="uq_heatmap_camera_hour_grid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    camera_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cameras.id", ondelete="CASCADE"))
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    frame_width: Mapped[int] = mapped_column(Integer)
    frame_height: Mapped[int] = mapped_column(Integer)
    grid_width: Mapped[int] = mapped_column(Integer)
    grid_height: Mapped[int] = mapped_column(Integer)
    cells: Mapped[bytes] = mapped_column(LargeBinary)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Nullable at the database level only, for the same reason as Camera.location_id: jobs
    # created before organizations existed are attached to one by the adoption step.
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True
    )
    video_source: Mapped[str] = mapped_column(Text)
    model_type: Mapped[str] = mapped_column(String(32))
    confidence_threshold: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    result: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
