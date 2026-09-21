import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, LargeBinary, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.modules import DEFAULT_MODULES


class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    rtsp_url: Mapped[str] = mapped_column(Text)
    username: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    encrypted_password: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Free text, not a foreign key: real Location rows don't exist until Phase 10.
    location_label: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
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
