import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.events import EVENT_TYPES
from app.modules import DEFAULT_MODULES


class AIModuleName(str, Enum):
    people = "people"
    vehicles = "vehicles"
    ocr = "ocr"
    qr = "qr"
    barcode = "barcode"


def _unique_module_ids(value):
    """Stored as plain strings in a JSONB list; a repeated tick collapses to one."""
    if value is None:
        return None
    return list(dict.fromkeys(m.value if isinstance(m, AIModuleName) else m for m in value))


# Built from app.events.EVENT_TYPES so the API's accepted values can't drift from the ones the
# tracking code emits.
EventTypeName = Enum("EventTypeName", {t: t for t in EVENT_TYPES}, type=str)


class ConnectionStatus(str, Enum):
    unknown = "unknown"
    online = "online"
    offline = "offline"


class TrackingStatusValue(str, Enum):
    starting = "starting"
    running = "running"
    reconnecting = "reconnecting"
    error = "error"
    stopped = "stopped"


class LineCountRead(BaseModel):
    line_id: str
    name: str
    # People. Named as in Phase 6 so existing clients keep working.
    in_count: int
    out_count: int
    vehicle_in_count: int = 0
    vehicle_out_count: int = 0


class ReadRead(BaseModel):
    """One thing a reading module has seen this session (a QR code, a barcode, or a line
    of text), deduplicated by kind + value. Not an event and not persisted — Phase 9."""

    kind: AIModuleName
    value: str
    # Symbology for QR/barcode ("QR Code", "Code 128"); OCR confidence for text.
    detail: str
    first_seen_at: datetime
    last_seen_at: datetime
    sightings: int


class ZoneCountRead(BaseModel):
    zone_id: str
    name: str
    count: int


class TrackingStatusRead(BaseModel):
    status: TrackingStatusValue
    error: Optional[str] = None
    frame_count: int = 0
    started_at: Optional[datetime] = None
    last_frame_at: Optional[datetime] = None
    active_track_ids: list[int] = Field(default_factory=list)
    active_vehicle_track_ids: list[int] = Field(default_factory=list)
    line_counts: list[LineCountRead] = Field(default_factory=list)
    zone_counts: list[ZoneCountRead] = Field(default_factory=list)
    reads: list[ReadRead] = Field(default_factory=list)


class LineCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    x1: float = Field(ge=0.0, le=1.0)
    y1: float = Field(ge=0.0, le=1.0)
    x2: float = Field(ge=0.0, le=1.0)
    y2: float = Field(ge=0.0, le=1.0)


class LineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    camera_id: uuid.UUID
    name: str
    x1: float
    y1: float
    x2: float
    y2: float
    created_at: datetime


class ZonePoint(BaseModel):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)


class ZoneCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    points: list[ZonePoint] = Field(min_length=3, max_length=100)


class ZoneRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    camera_id: uuid.UUID
    name: str
    points: list[ZonePoint]
    created_at: datetime


class CameraCreate(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    name: str = Field(min_length=1, max_length=200)
    rtsp_url: str = Field(min_length=1)
    username: Optional[str] = Field(default=None, max_length=200)
    password: Optional[str] = None
    # Omit to use the organization's default location.
    location_id: Optional[uuid.UUID] = None
    notes: Optional[str] = None
    enabled_modules: list[AIModuleName] = Field(default_factory=lambda: list(DEFAULT_MODULES))

    _dedupe_modules = field_validator("enabled_modules", mode="after")(_unique_module_ids)


class CameraUpdate(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    rtsp_url: Optional[str] = Field(default=None, min_length=1)
    username: Optional[str] = Field(default=None, max_length=200)
    # Omit entirely to leave the stored password unchanged; "" clears it.
    password: Optional[str] = None
    # Omit to leave the camera's location unchanged; a camera always belongs to one.
    location_id: Optional[uuid.UUID] = None
    notes: Optional[str] = None
    # Omit to leave the selection unchanged; [] is allowed (tracking just won't start
    # until at least one module is enabled).
    enabled_modules: Optional[list[AIModuleName]] = None

    _dedupe_modules = field_validator("enabled_modules", mode="after")(_unique_module_ids)


class CameraRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    rtsp_url: str
    username: Optional[str] = None
    has_password: bool
    location_id: uuid.UUID
    location_name: str
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    connection_status: ConnectionStatus
    last_tested_at: Optional[datetime] = None
    last_error: Optional[str] = None
    last_fps: Optional[float] = None
    last_width: Optional[int] = None
    last_height: Optional[int] = None
    enabled_modules: list[AIModuleName]


def camera_to_read(camera) -> "CameraRead":
    """`has_password` and `location_name` are derived, not columns, so they can't come from
    from_attributes alone. Requires `camera.location` to be loaded (every route that
    returns a camera joins or loads it — see routers/cameras.py)."""
    return CameraRead(
        id=camera.id,
        name=camera.name,
        rtsp_url=camera.rtsp_url,
        username=camera.username,
        has_password=camera.encrypted_password is not None,
        location_id=camera.location_id,
        location_name=camera.location.name,
        notes=camera.notes,
        created_at=camera.created_at,
        updated_at=camera.updated_at,
        connection_status=camera.connection_status,
        last_tested_at=camera.last_tested_at,
        last_error=camera.last_error,
        last_fps=camera.last_fps,
        last_width=camera.last_width,
        last_height=camera.last_height,
        enabled_modules=camera.enabled_modules,
    )


class ModelType(str, Enum):
    yolo = "yolo"
    yolo_seg = "yolo_seg"
    yolo_pose = "yolo_pose"


class JobStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class JobCreateRequest(BaseModel):
    video_source: str
    model_type: ModelType
    confidence_threshold: float = Field(default=0.25, ge=0.0, le=1.0)


class JobCreateResponse(BaseModel):
    id: str


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    video_source: str
    model_type: ModelType
    confidence_threshold: float
    status: JobStatus
    created_at: datetime
    result: Optional[dict] = None
    error: Optional[str] = None


class EventRead(BaseModel):
    """One stored event (see docs/ARCHITECTURE.md, "Event schema")."""

    id: uuid.UUID
    camera_id: uuid.UUID
    camera_name: str
    occurred_at: datetime
    event_type: EventTypeName
    category: Optional[str] = None
    direction: Optional[str] = None
    subject_id: Optional[uuid.UUID] = None
    subject_name: Optional[str] = None
    value: Optional[str] = None
    detail: Optional[str] = None


class EventListRead(BaseModel):
    events: list[EventRead]
    # Pass back as `before` to get the next (older) page; null when this was the last one.
    next_before: Optional[str] = None


class LineSummaryRead(BaseModel):
    line_id: Optional[uuid.UUID] = None
    name: Optional[str] = None
    people_in: int
    people_out: int
    vehicle_in: int
    vehicle_out: int


class ZoneSummaryRead(BaseModel):
    zone_id: Optional[uuid.UUID] = None
    name: Optional[str] = None
    entered: int
    exited: int


class ReadsSummaryRead(BaseModel):
    qr: int
    barcode: int
    ocr: int


class AnalyticsSummaryRead(BaseModel):
    since: datetime
    until: datetime
    people_in: int
    people_out: int
    vehicle_in: int
    vehicle_out: int
    lines: list[LineSummaryRead]
    zones: list[ZoneSummaryRead]
    reads: ReadsSummaryRead
    # Camera-seconds that tracking was actually running in the range (summed over cameras).
    tracked_seconds: float


class TimeseriesPointRead(BaseModel):
    start: datetime
    end: datetime
    people_in: int
    people_out: int
    vehicle_in: int
    vehicle_out: int
    zone_entered: int
    zone_exited: int
    reads: int
    # 0 means nothing was being tracked: "not running", not "no traffic".
    tracked_seconds: float


class TimeseriesRead(BaseModel):
    bucket: str
    tz: str
    since: datetime
    until: datetime
    points: list[TimeseriesPointRead]


class HeatmapInfoRead(BaseModel):
    camera_id: uuid.UUID
    available: bool
    samples: int = 0
    frame_width: Optional[int] = None
    frame_height: Optional[int] = None
    grid_width: Optional[int] = None
    grid_height: Optional[int] = None
    first_period: Optional[datetime] = None
    last_period: Optional[datetime] = None
    ignored_samples: int = 0
