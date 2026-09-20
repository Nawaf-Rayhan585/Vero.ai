import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


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


class TrackingStatusRead(BaseModel):
    status: TrackingStatusValue
    error: Optional[str] = None
    frame_count: int = 0
    started_at: Optional[datetime] = None
    last_frame_at: Optional[datetime] = None
    active_track_ids: list[int] = Field(default_factory=list)


class CameraCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    rtsp_url: str = Field(min_length=1)
    username: Optional[str] = Field(default=None, max_length=200)
    password: Optional[str] = None
    location_label: Optional[str] = Field(default=None, max_length=200)
    notes: Optional[str] = None


class CameraUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    rtsp_url: Optional[str] = Field(default=None, min_length=1)
    username: Optional[str] = Field(default=None, max_length=200)
    # Omit entirely to leave the stored password unchanged; "" clears it.
    password: Optional[str] = None
    location_label: Optional[str] = Field(default=None, max_length=200)
    notes: Optional[str] = None


class CameraRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    rtsp_url: str
    username: Optional[str] = None
    has_password: bool
    location_label: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    connection_status: ConnectionStatus
    last_tested_at: Optional[datetime] = None
    last_error: Optional[str] = None
    last_fps: Optional[float] = None
    last_width: Optional[int] = None
    last_height: Optional[int] = None


def camera_to_read(camera) -> "CameraRead":
    """`has_password` is derived, not a column, so it can't come from from_attributes alone."""
    return CameraRead(
        id=camera.id,
        name=camera.name,
        rtsp_url=camera.rtsp_url,
        username=camera.username,
        has_password=camera.encrypted_password is not None,
        location_label=camera.location_label,
        notes=camera.notes,
        created_at=camera.created_at,
        updated_at=camera.updated_at,
        connection_status=camera.connection_status,
        last_tested_at=camera.last_tested_at,
        last_error=camera.last_error,
        last_fps=camera.last_fps,
        last_width=camera.last_width,
        last_height=camera.last_height,
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
