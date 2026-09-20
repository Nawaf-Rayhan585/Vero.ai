"""In-memory, ephemeral continuous detection+tracking sessions, one per camera.

Session state (frame count, active tracks, line-crossing counts, zone occupancy, the
heatmap) is deliberately not persisted: no "enabled" flag, no auto-resume after a backend
restart, everything resets every time tracking starts. Line and zone *definitions*
(app.models.Line / Zone) are real, persisted configuration, loaded once when a session
starts. Historical/aggregated analytics is Phase 9's job — this module only proves
detection+tracking+counting works and is watchable while a session runs.
"""
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import cv2
import numpy as np
from ultralytics import YOLO

from app.camera_testing import build_stream_url
from app.counting import LineConfig, Point, ResolvedLine, classify_crossing
from app.heatmap import HeatmapAccumulator
from app.zones import ResolvedZone, ZoneConfig, point_in_polygon

MODEL_WEIGHTS = "yolov8n.pt"
PERSON_CLASS_ID = 0

# Measured on this project's dev machine (CPU-only, 4-core i3): steady-state inference
# is ~0.09s/frame, so 5fps leaves headroom for the backend to keep serving other
# requests rather than chasing this session's ~10fps ceiling.
TARGET_FPS = 5.0
MIN_FRAME_INTERVAL_SECONDS = 1.0 / TARGET_FPS

OPEN_TIMEOUT_MS = 5000
READ_TIMEOUT_MS = 5000
RECONNECT_INTERVAL_SECONDS = 5.0
MAX_RECONNECT_ATTEMPTS = 12  # ~60s total, matching the plan's confirmed reconnect policy

BOX_COLOR = (0, 200, 0)
LINE_COLOR = (255, 165, 0)
ZONE_COLOR = (0, 215, 255)
ZONE_FILL_ALPHA = 0.2


def should_give_up(attempt: int) -> bool:
    """Pure and independently testable, separate from the real-time retry loop."""
    return attempt >= MAX_RECONNECT_ATTEMPTS


@dataclass
class TrackingStatusSnapshot:
    status: str
    error: Optional[str]
    frame_count: int
    started_at: Optional[datetime]
    last_frame_at: Optional[datetime]
    active_track_ids: list = field(default_factory=list)
    line_counts: list = field(default_factory=list)
    zone_counts: list = field(default_factory=list)


def _open_capture(stream_url: str) -> Optional[cv2.VideoCapture]:
    cap = cv2.VideoCapture(
        stream_url,
        cv2.CAP_FFMPEG,
        [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, OPEN_TIMEOUT_MS, cv2.CAP_PROP_READ_TIMEOUT_MSEC, READ_TIMEOUT_MS],
    )
    if cap.isOpened():
        return cap
    cap.release()
    return None


def _draw_zones(frame, resolved_zones: list[ResolvedZone], zone_counts: dict) -> None:
    """Drawn first so person boxes and lines sit on top of the translucent fill."""
    if not resolved_zones:
        return
    polygons = [np.array([[int(p.x), int(p.y)] for p in rz.polygon], dtype=np.int32) for rz in resolved_zones]

    overlay = frame.copy()
    for polygon in polygons:
        cv2.fillPoly(overlay, [polygon], ZONE_COLOR)
    cv2.addWeighted(overlay, ZONE_FILL_ALPHA, frame, 1 - ZONE_FILL_ALPHA, 0, dst=frame)

    for rz, polygon in zip(resolved_zones, polygons):
        cv2.polylines(frame, [polygon], True, ZONE_COLOR, 2)
        label = f"{rz.name}: {zone_counts.get(rz.id, 0)} inside"
        cv2.putText(
            frame,
            label,
            (int(polygon[:, 0].min()), max(int(polygon[:, 1].min()) - 8, 0)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            ZONE_COLOR,
            2,
        )


def _draw_and_encode(
    frame,
    result,
    resolved_lines: list[ResolvedLine],
    line_counts: dict,
    resolved_zones: list[ResolvedZone],
    zone_counts: dict,
) -> tuple[Optional[bytes], list]:
    _draw_zones(frame, resolved_zones, zone_counts)

    track_ids: list[int] = []
    for box in result.boxes:
        x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
        track_id = int(box.id.item()) if box.id is not None else None
        if track_id is not None:
            track_ids.append(track_id)
        label = f"person #{track_id}" if track_id is not None else "person"
        cv2.rectangle(frame, (x1, y1), (x2, y2), BOX_COLOR, 2)
        cv2.putText(frame, label, (x1, max(y1 - 8, 0)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, BOX_COLOR, 2)

    for rl in resolved_lines:
        counts = line_counts.get(rl.id, {"in": 0, "out": 0})
        p1 = (int(rl.line.x1), int(rl.line.y1))
        p2 = (int(rl.line.x2), int(rl.line.y2))
        cv2.line(frame, p1, p2, LINE_COLOR, 2)
        label = f"{rl.name}: {counts['in']} in / {counts['out']} out"
        cv2.putText(
            frame,
            label,
            (min(p1[0], p2[0]), max(min(p1[1], p2[1]) - 8, 0)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            LINE_COLOR,
            2,
        )

    ok, encoded = cv2.imencode(".jpg", frame)
    return (encoded.tobytes() if ok else None), track_ids


def _track_points(result) -> dict:
    """Bottom-center of each tracked box (feet position) — more accurate for
    ground-plane line crossing than the box center."""
    points: dict[int, Point] = {}
    for box in result.boxes:
        if box.id is None:
            continue
        track_id = int(box.id.item())
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        points[track_id] = Point((x1 + x2) / 2, y2)
    return points


class TrackingSession:
    def __init__(
        self,
        camera_id: uuid.UUID,
        rtsp_url: str,
        username: Optional[str],
        password: Optional[str],
        lines: Optional[list[LineConfig]] = None,
        zones: Optional[list[ZoneConfig]] = None,
    ):
        self.camera_id = camera_id
        self._stream_url = build_stream_url(rtsp_url, username, password)
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

        self._status = "starting"
        self._error: Optional[str] = None
        self._frame_count = 0
        self._started_at = datetime.now(timezone.utc)
        self._last_frame_at: Optional[datetime] = None
        self._active_track_ids: list[int] = []
        self._latest_jpeg: Optional[bytes] = None
        # The annotated ndarray behind _latest_jpeg. Kept so the heatmap can be blended
        # onto it on request, rather than encoding a second JPEG every frame for a view
        # most of the time nobody is looking at. Replaced, never mutated, once stored.
        self._latest_frame: Optional[np.ndarray] = None

        # Lines and zones are loaded once at session start (a snapshot, like credentials)
        # — not re-queried mid-session. Resolved to pixel space lazily, once the first
        # real frame reveals this camera's actual resolution.
        self._line_configs: list[LineConfig] = lines or []
        self._resolved_lines: Optional[list[ResolvedLine]] = None
        self._previous_positions: dict[int, Point] = {}
        self._line_counts: dict[uuid.UUID, dict[str, int]] = {lc.id: {"in": 0, "out": 0} for lc in self._line_configs}

        self._zone_configs: list[ZoneConfig] = zones or []
        self._resolved_zones: Optional[list[ResolvedZone]] = None
        self._zone_counts: dict[uuid.UUID, int] = {zc.id: 0 for zc in self._zone_configs}

        self._heatmap: Optional[HeatmapAccumulator] = None

        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=READ_TIMEOUT_MS / 1000 + 5)

    def snapshot(self) -> TrackingStatusSnapshot:
        with self._lock:
            line_counts = [
                {
                    "line_id": str(lc.id),
                    "name": lc.name,
                    "in_count": self._line_counts[lc.id]["in"],
                    "out_count": self._line_counts[lc.id]["out"],
                }
                for lc in self._line_configs
            ]
            zone_counts = [
                {"zone_id": str(zc.id), "name": zc.name, "count": self._zone_counts[zc.id]}
                for zc in self._zone_configs
            ]
            return TrackingStatusSnapshot(
                status=self._status,
                error=self._error,
                frame_count=self._frame_count,
                started_at=self._started_at,
                last_frame_at=self._last_frame_at,
                active_track_ids=list(self._active_track_ids),
                line_counts=line_counts,
                zone_counts=zone_counts,
            )

    def latest_frame(self, heatmap: bool = False) -> Optional[bytes]:
        """The latest annotated JPEG; with `heatmap=True`, the same frame with the
        accumulated heat overlay blended on (encoded on demand). Falls back to the plain
        frame if no heat has been collected yet."""
        with self._lock:
            jpeg = self._latest_jpeg
            frame = self._latest_frame
            accumulator = self._heatmap
        if not heatmap or frame is None or accumulator is None:
            return jpeg
        ok, encoded = cv2.imencode(".jpg", accumulator.render(frame))
        return encoded.tobytes() if ok else jpeg

    def _set_status(self, status: str, error: Optional[str] = None) -> None:
        with self._lock:
            self._status = status
            self._error = error

    def _update_counts(self, track_points: dict) -> None:
        """Compares each currently-visible track's position against its last-seen
        position to detect line crossings. Independently testable by calling directly
        with synthetic sequential positions — no video/model required."""
        if self._resolved_lines:
            for track_id, curr in track_points.items():
                prev = self._previous_positions.get(track_id)
                if prev is None:
                    continue
                for rl in self._resolved_lines:
                    direction = classify_crossing(rl.line, prev, curr)
                    if direction is not None:
                        with self._lock:
                            self._line_counts[rl.id][direction] += 1
        self._previous_positions = track_points

    def _update_zones(self, track_points: dict) -> None:
        """How many currently-visible tracks stand inside each zone. A live count of this
        frame only — nothing accumulates, so a zone with nobody in it reads 0. Directly
        testable with synthetic positions, like `_update_counts`."""
        if not self._resolved_zones:
            return
        counts = {
            rz.id: sum(1 for point in track_points.values() if point_in_polygon(point, rz.polygon))
            for rz in self._resolved_zones
        }
        with self._lock:
            self._zone_counts = counts

    def _record_frame(self, jpeg: Optional[bytes], track_ids: list, annotated_frame: np.ndarray) -> None:
        with self._lock:
            self._status = "running"
            self._frame_count += 1
            self._last_frame_at = datetime.now(timezone.utc)
            self._active_track_ids = track_ids
            if jpeg is not None:
                self._latest_jpeg = jpeg
                self._latest_frame = annotated_frame

    def _reconnect_loop(self) -> Optional[cv2.VideoCapture]:
        """Returns a freshly opened capture, or None if stopped/gave up."""
        attempt = 0
        self._set_status("reconnecting")
        while not self._stop_event.is_set():
            if should_give_up(attempt):
                self._set_status("error", "Camera unreachable after repeated reconnect attempts")
                return None
            if self._stop_event.wait(RECONNECT_INTERVAL_SECONDS):
                return None
            attempt += 1
            cap = _open_capture(self._stream_url)
            if cap is not None:
                return cap
        return None

    def _run(self) -> None:
        model = YOLO(MODEL_WEIGHTS)
        cap = _open_capture(self._stream_url)
        if cap is None:
            self._set_status("error", "Could not open stream (unreachable, refused, or unsupported)")
            return
        self._set_status("running")

        try:
            while not self._stop_event.is_set():
                loop_start = time.monotonic()
                ok, frame = cap.read()

                if not ok or frame is None:
                    cap.release()
                    cap = self._reconnect_loop()
                    if cap is None:
                        return
                    continue

                if self._resolved_lines is None:
                    height, width = frame.shape[:2]
                    self._resolved_lines = [lc.to_pixels(width, height) for lc in self._line_configs]
                    self._resolved_zones = [zc.to_pixels(width, height) for zc in self._zone_configs]
                    with self._lock:
                        self._heatmap = HeatmapAccumulator(width, height)

                results = model.track(
                    frame, persist=True, classes=[PERSON_CLASS_ID], tracker="bytetrack.yaml", verbose=False
                )
                result = results[0]
                track_points = _track_points(result)
                self._update_counts(track_points)
                self._update_zones(track_points)
                self._heatmap.add(track_points.values())
                jpeg, track_ids = _draw_and_encode(
                    frame, result, self._resolved_lines, self._line_counts, self._resolved_zones, self._zone_counts
                )
                self._record_frame(jpeg, track_ids, frame)

                remaining = MIN_FRAME_INTERVAL_SECONDS - (time.monotonic() - loop_start)
                if remaining > 0:
                    self._stop_event.wait(remaining)
        finally:
            # cap can be None here: _reconnect_loop() returns None both when it gives
            # up (already released its last attempt) and when stop() interrupts a wait.
            if cap is not None:
                cap.release()
            with self._lock:
                if self._status != "error":
                    self._status = "stopped"


class TrackingManager:
    def __init__(self):
        self._sessions: dict[uuid.UUID, TrackingSession] = {}
        self._lock = threading.Lock()

    def start(
        self,
        camera_id: uuid.UUID,
        rtsp_url: str,
        username: Optional[str],
        password: Optional[str],
        lines: Optional[list[LineConfig]] = None,
        zones: Optional[list[ZoneConfig]] = None,
    ) -> TrackingSession:
        with self._lock:
            existing = self._sessions.get(camera_id)
            if existing is not None and existing.snapshot().status in ("starting", "running", "reconnecting"):
                return existing
            session = TrackingSession(camera_id, rtsp_url, username, password, lines, zones)
            self._sessions[camera_id] = session
        session.start()
        return session

    def stop(self, camera_id: uuid.UUID) -> bool:
        with self._lock:
            session = self._sessions.pop(camera_id, None)
        if session is None:
            return False
        session.stop()
        return True

    def get(self, camera_id: uuid.UUID) -> Optional[TrackingSession]:
        with self._lock:
            return self._sessions.get(camera_id)

    def stop_all(self) -> None:
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            session.stop()


tracking_manager = TrackingManager()
