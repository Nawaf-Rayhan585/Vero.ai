import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func, text
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
