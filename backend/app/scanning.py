"""The reading modules: QR codes, barcodes and on-screen text (OCR).

Everything a session reads is ephemeral, like every other tracking-session value: it lives
in a `ReadRegistry` in memory and starts empty every time tracking starts. Turning reads
into stored events and history is Phase 9's job.

QR/barcode decoding (zxing-cpp) is cheap enough (~20 ms per 720p frame) to run inline on
frames. OCR (RapidOCR, PaddleOCR's models via ONNX Runtime) costs ~1 s per pass on a CPU
and, run alongside YOLO, roughly doubles YOLO's per-frame time (measured while planning
this phase) — so it runs on its own background thread on a multi-second cadence and the
tracking loop only ever hands it a frame, never waits for it.
"""
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Iterable, Optional

import numpy as np
import zxingcpp

from app.modules import BARCODE, OCR, QR

logger = logging.getLogger(__name__)

# A read's kind is the id of the module that produced it.
KIND_QR = QR
KIND_BARCODE = BARCODE
KIND_TEXT = OCR

_BF = zxingcpp.BarcodeFormat
_QR_FAMILY = [_BF.QRCode, _BF.MicroQRCode, _BF.RMQRCode]
# Every other readable symbology a warehouse/retail camera is likely to see: all 1D
# codes (EAN/UPC, Code 128, Code 39, ITF, ...) plus the common 2D non-QR codes.
_BARCODE_FAMILY = [_BF.AllLinear, _BF.DataMatrix, _BF.PDF417, _BF.Aztec]

MIN_TEXT_CONFIDENCE = 0.6
MIN_TEXT_LENGTH = 2
# How long OCR waits after finishing a pass before it will accept another frame.
OCR_INTERVAL_SECONDS = 5.0
# Caps ONNX Runtime's threads so an OCR pass can't grab every core from the tracker.
OCR_THREADS = 2

# A value seen again after this long counts as a new sighting; one that stays in view
# counts once, not once per frame.
SIGHTING_GAP_SECONDS = 5.0
MAX_READS = 50
# How long after it was last seen a read keeps its box drawn on the video.
OVERLAY_WINDOW_SECONDS = 4.0

Points = list[tuple[float, float]]


@dataclass(frozen=True)
class CodeRead:
    kind: str
    value: str
    detail: str  # symbology name, e.g. "QR Code" / "Code 128"
    points: Points


@dataclass(frozen=True)
class TextRead:
    value: str
    confidence: float
    points: Points


class CodeScanner:
    """Decodes QR codes and/or barcodes, depending on which modules are enabled. Limiting
    the formats is also what stops a QR-only camera from reporting a stray barcode."""

    def __init__(self, modules: Iterable[str]):
        modules = set(modules)
        self._formats: list = []
        if QR in modules:
            self._formats += _QR_FAMILY
        if BARCODE in modules:
            self._formats += _BARCODE_FAMILY

    @property
    def enabled(self) -> bool:
        """False when neither the QR nor the barcode module is on: nothing to decode."""
        return bool(self._formats)

    def scan(self, frame: np.ndarray) -> list[CodeRead]:
        if not self._formats:
            return []
        reads = []
        for result in zxingcpp.read_barcodes(frame, formats=self._formats):
            if not result.valid or not result.text:
                continue
            p = result.position
            reads.append(
                CodeRead(
                    kind=KIND_QR if result.format in _QR_FAMILY else KIND_BARCODE,
                    value=result.text,
                    detail=str(result.format),
                    points=[(float(c.x), float(c.y)) for c in (p.top_left, p.top_right, p.bottom_right, p.bottom_left)],
                )
            )
        return reads


def _create_rapidocr():
    # Imported here, not at module level: it pulls in ONNX Runtime and is only needed by
    # sessions that actually run the OCR module.
    from rapidocr import RapidOCR

    return RapidOCR(
        params={
            "Global.log_level": "warning",
            "EngineConfig.onnxruntime.intra_op_num_threads": OCR_THREADS,
        }
    )


class TextReader:
    """Reads text in a frame. The engine is created lazily on the first read (model load
    is ~1 s) and is injectable so the filtering below is testable without running OCR."""

    def __init__(self, engine_factory: Optional[Callable[[], Callable]] = None):
        self._engine_factory = engine_factory or _create_rapidocr
        self._engine: Optional[Callable] = None

    def read(self, frame: np.ndarray) -> list[TextRead]:
        if self._engine is None:
            self._engine = self._engine_factory()
        result = self._engine(frame)
        if result.txts is None or result.boxes is None or result.scores is None:
            return []
        reads = []
        for box, text, score in zip(result.boxes, result.txts, result.scores):
            text = text.strip()
            if float(score) < MIN_TEXT_CONFIDENCE or len(text) < MIN_TEXT_LENGTH:
                continue
            reads.append(
                TextRead(value=text, confidence=float(score), points=[(float(x), float(y)) for x, y in box])
            )
        return reads


@dataclass
class ReadEntry:
    kind: str
    value: str
    detail: str
    first_seen_at: datetime
    last_seen_at: datetime
    sightings: int
    points: Points = field(default_factory=list)
    last_seen_monotonic: float = 0.0


class ReadRegistry:
    """Thread-safe, in-memory, deduplicated by (kind, value). Written by the tracking
    loop and the OCR worker, read by request threads."""

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        on_new_sighting: Optional[Callable[[str, str, str], None]] = None,
    ):
        self._clock = clock
        self._wall_clock = wall_clock
        # Called (kind, value, detail) once per new sighting — the first time a value is
        # seen, or again after the sighting gap — never once per frame. This is where a
        # read becomes a stored event.
        self._on_new_sighting = on_new_sighting
        self._lock = threading.Lock()
        self._entries: dict[tuple[str, str], ReadEntry] = {}

    def record(self, kind: str, value: str, detail: str, points: Points) -> bool:
        """Returns whether this was a new sighting (see `on_new_sighting`)."""
        now, wall = self._clock(), self._wall_clock()
        new_sighting = False
        with self._lock:
            entry = self._entries.get((kind, value))
            if entry is None:
                self._entries[(kind, value)] = ReadEntry(kind, value, detail, wall, wall, 1, points, now)
                self._evict_oldest_beyond_cap()
                new_sighting = True
            else:
                if now - entry.last_seen_monotonic > SIGHTING_GAP_SECONDS:
                    entry.sightings += 1
                    new_sighting = True
                entry.last_seen_at = wall
                entry.last_seen_monotonic = now
                entry.detail = detail
                entry.points = points
        # Outside the lock: the callback may do slow or re-entrant work.
        if new_sighting and self._on_new_sighting is not None:
            try:
                self._on_new_sighting(kind, value, detail)
            except Exception:
                logger.exception("on_new_sighting callback failed")
        return new_sighting

    def _evict_oldest_beyond_cap(self) -> None:
        while len(self._entries) > MAX_READS:
            oldest = min(self._entries, key=lambda k: self._entries[k].last_seen_monotonic)
            del self._entries[oldest]

    def snapshot(self) -> list[dict]:
        """Most recently seen first."""
        with self._lock:
            entries = sorted(self._entries.values(), key=lambda e: e.last_seen_monotonic, reverse=True)
            return [
                {
                    "kind": e.kind,
                    "value": e.value,
                    "detail": e.detail,
                    "first_seen_at": e.first_seen_at,
                    "last_seen_at": e.last_seen_at,
                    "sightings": e.sightings,
                }
                for e in entries
            ]

    def recent_overlays(self) -> list[ReadEntry]:
        """Reads seen within the overlay window, for drawing on the video — a read stays
        visible for a few seconds instead of flickering with every scan."""
        now = self._clock()
        with self._lock:
            return [
                ReadEntry(e.kind, e.value, e.detail, e.first_seen_at, e.last_seen_at, e.sightings, list(e.points), e.last_seen_monotonic)
                for e in self._entries.values()
                if now - e.last_seen_monotonic <= OVERLAY_WINDOW_SECONDS and e.points
            ]


class OcrWorker:
    """Runs OCR on a background thread so the tracking loop never waits on it. The loop
    offers a frame copy only when `wants_frame()` says the worker is idle and its
    cool-down has passed; the worker stops with the session's stop event."""

    def __init__(
        self,
        reader: TextReader,
        registry: ReadRegistry,
        stop_event: threading.Event,
        interval_seconds: float = OCR_INTERVAL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._reader = reader
        self._registry = registry
        self._stop_event = stop_event
        self._interval = interval_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._pending: Optional[np.ndarray] = None
        self._busy = False
        self._next_allowed_at = 0.0
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    @property
    def started(self) -> bool:
        return self._thread.ident is not None

    def join(self, timeout: Optional[float] = None) -> None:
        self._thread.join(timeout=timeout)

    def wants_frame(self) -> bool:
        with self._lock:
            return self._pending is None and not self._busy and self._clock() >= self._next_allowed_at

    def submit(self, frame: np.ndarray) -> None:
        with self._lock:
            self._pending = frame
        self._wake.set()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._wake.wait(timeout=0.5)
            with self._lock:
                frame, self._pending = self._pending, None
                self._busy = frame is not None
                self._wake.clear()
            if frame is None:
                continue
            try:
                for read in self._reader.read(frame):
                    self._registry.record(KIND_TEXT, read.value, f"{read.confidence:.2f}", read.points)
            except Exception:
                # A failed pass (e.g. the model couldn't load) must not kill the worker or
                # the tracking session it belongs to; it just tries again next interval.
                logger.exception("OCR pass failed")
            finally:
                with self._lock:
                    self._busy = False
                    self._next_allowed_at = self._clock() + self._interval


def ascii_label(text: str) -> str:
    """OpenCV's putText can only draw ASCII; anything else would render as '?' boxes."""
    return re.sub(r"[^\x20-\x7e]", "?", text)
