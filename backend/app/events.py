"""Event generation's write path: structured events and hourly heatmap snapshots.

Tracking threads call `EventRecorder.record()` and move on: it never blocks and never
raises, so a slow or broken database can't stall or kill a camera's tracking. A single
background thread drains a bounded queue and batch-inserts.

Delivery is **at-most-once**. A batch whose write fails for a transient reason (the
database is down) is retried with backoff, but the queue is in memory: a hard crash loses
whatever was queued (about a second's worth in normal operation), a full queue drops new
events (counted in `dropped`), and an event that can never be written — its camera was
deleted mid-session — is dropped on its own without holding up the rest.

Events hold structured facts only. Never video, never images.
"""
import logging
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional, Union

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.database import SessionLocal
from app.heatmap import decode_grid, encode_grid
from app.models import Event, HeatmapSnapshot

logger = logging.getLogger(__name__)

# Event types. The uptime ones are what lets analytics tell "nobody came" from "not running".
LINE_CROSSED = "line_crossed"
ZONE_ENTERED = "zone_entered"
ZONE_EXITED = "zone_exited"
READ = "read"
TRACKING_STARTED = "tracking_started"
TRACKING_STOPPED = "tracking_stopped"
TRACKING_ERROR = "tracking_error"
TRACKING_RECONNECTING = "tracking_reconnecting"
TRACKING_RESUMED = "tracking_resumed"

EVENT_TYPES = (
    LINE_CROSSED,
    ZONE_ENTERED,
    ZONE_EXITED,
    READ,
    TRACKING_STARTED,
    TRACKING_STOPPED,
    TRACKING_ERROR,
    TRACKING_RECONNECTING,
    TRACKING_RESUMED,
)
# Tracking is producing data after these...
UPTIME_RUNNING_TYPES = (TRACKING_STARTED, TRACKING_RESUMED)
# ...and not after these.
UPTIME_NOT_RUNNING_TYPES = (TRACKING_STOPPED, TRACKING_ERROR, TRACKING_RECONNECTING)
UPTIME_EVENT_TYPES = UPTIME_RUNNING_TYPES + UPTIME_NOT_RUNNING_TYPES

MAX_QUEUE = 10_000
BATCH_SIZE = 200
IDLE_WAIT_SECONDS = 0.5
RETRY_BACKOFF_SECONDS = (0.5, 1.0, 2.0, 5.0)


@dataclass(frozen=True)
class NewEvent:
    camera_id: uuid.UUID
    event_type: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    category: Optional[str] = None
    direction: Optional[str] = None
    subject_id: Optional[uuid.UUID] = None
    subject_name: Optional[str] = None
    value: Optional[str] = None
    detail: Optional[str] = None


@dataclass(frozen=True)
class HeatDelta:
    """Heat accumulated by one camera since the last hand-off, to be merged into that
    hour's stored snapshot."""

    camera_id: uuid.UUID
    period_start: datetime  # the UTC hour it is attributed to
    frame_width: int
    frame_height: int
    grid: np.ndarray  # uint32, (grid_height, grid_width)
    samples: int


Item = Union[NewEvent, HeatDelta]


def hour_start(moment: datetime) -> datetime:
    return moment.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def _add_item(db, item: Item) -> None:
    if isinstance(item, NewEvent):
        db.add(
            Event(
                camera_id=item.camera_id,
                occurred_at=item.occurred_at,
                event_type=item.event_type,
                category=item.category,
                direction=item.direction,
                subject_id=item.subject_id,
                subject_name=item.subject_name,
                value=item.value,
                detail=item.detail,
            )
        )
        return

    grid_height, grid_width = item.grid.shape
    existing = db.scalar(
        select(HeatmapSnapshot)
        .where(
            HeatmapSnapshot.camera_id == item.camera_id,
            HeatmapSnapshot.period_start == item.period_start,
            HeatmapSnapshot.grid_width == grid_width,
            HeatmapSnapshot.grid_height == grid_height,
        )
        .with_for_update()
    )
    if existing is None:
        db.add(
            HeatmapSnapshot(
                camera_id=item.camera_id,
                period_start=item.period_start,
                frame_width=item.frame_width,
                frame_height=item.frame_height,
                grid_width=grid_width,
                grid_height=grid_height,
                cells=encode_grid(item.grid),
                sample_count=item.samples,
            )
        )
    else:
        merged = decode_grid(existing.cells, grid_width, grid_height) + item.grid
        existing.cells = encode_grid(merged)
        existing.sample_count += item.samples
        existing.frame_width, existing.frame_height = item.frame_width, item.frame_height
        existing.updated_at = datetime.now(timezone.utc)


class EventRecorder:
    def __init__(
        self,
        session_factory: Callable = SessionLocal,
        max_queue: int = MAX_QUEUE,
        batch_size: int = BATCH_SIZE,
        idle_wait: float = IDLE_WAIT_SECONDS,
        retry_backoff: tuple = RETRY_BACKOFF_SECONDS,
    ):
        self._session_factory = session_factory
        self._queue: "queue.Queue[Item]" = queue.Queue(maxsize=max_queue)
        self._batch_size = batch_size
        self._idle_wait = idle_wait
        self._retry_backoff = retry_backoff
        self._start_lock = threading.Lock()
        self._counter_lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        # Written only by the writer thread; kept across loop turns so a failed batch is
        # retried before anything newer.
        self._retrying: list[Item] = []
        self.dropped = 0  # queue full, or unwritable
        self.written = 0

    # -- producer side (tracking threads) ------------------------------------------------

    def record(self, item: Item) -> None:
        """Queues an event or heat delta. Never blocks, never raises."""
        try:
            self._ensure_started()
            self._queue.put_nowait(item)
        except queue.Full:
            self._count_dropped(1)
            logger.warning("Event queue full; dropped a %s", type(item).__name__)
        except Exception:
            logger.exception("Could not queue an event")

    def _ensure_started(self) -> None:
        # Lazily, so nothing has to remember to start it: a TestClient without a lifespan
        # and a script both just work.
        if self._thread is not None and self._thread.is_alive():
            return
        with self._start_lock:
            if self._thread is None or not self._thread.is_alive():
                self._stop_event.clear()
                self._thread = threading.Thread(target=self._run, name="event-recorder", daemon=True)
                self._thread.start()

    def _count_dropped(self, n: int) -> None:
        with self._counter_lock:
            self.dropped += n

    # -- lifecycle -------------------------------------------------------------------------

    def flush(self, timeout: float = 15.0) -> bool:
        """Blocks until everything queued so far has been written or dropped. For tests
        and orderly shutdown; returns False if the timeout ran out first."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._queue.unfinished_tasks == 0:
                return True
            time.sleep(0.01)
        return self._queue.unfinished_tasks == 0

    def stop(self, timeout: float = 15.0) -> None:
        """Drains what is queued (one more try if the database is down, then it gives
        up) and stops the writer thread."""
        thread = self._thread
        if thread is None:
            return
        self._stop_event.set()
        thread.join(timeout=timeout)

    # -- writer thread ---------------------------------------------------------------------

    def _collect_batch(self) -> list[Item]:
        batch: list[Item] = []
        try:
            batch.append(self._queue.get(timeout=self._idle_wait))
        except queue.Empty:
            return batch
        while len(batch) < self._batch_size:
            try:
                batch.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return batch

    def _run(self) -> None:
        failures = 0
        while True:
            batch = self._retrying or self._collect_batch()
            self._retrying = []
            if not batch:
                if self._stop_event.is_set():
                    return
                continue

            unwritten, unwritable = self._write_batch(batch)
            handled = len(batch) - len(unwritten)
            for _ in range(handled):
                self._queue.task_done()
            with self._counter_lock:
                self.written += handled - unwritable

            if not unwritten:
                failures = 0
                continue

            if self._stop_event.is_set():
                # Shutting down with the database unavailable: one try was enough.
                logger.error("Dropping %d event(s): the database is unavailable at shutdown", len(unwritten))
                self._count_dropped(len(unwritten))
                for _ in unwritten:
                    self._queue.task_done()
                continue

            self._retrying = unwritten
            delay = self._retry_backoff[min(failures, len(self._retry_backoff) - 1)]
            failures += 1
            self._stop_event.wait(delay)

    def _write_batch(self, batch: list[Item]) -> tuple[list[Item], int]:
        """Writes `batch`. Returns (items not written *yet*, how many were dropped as
        unwritable). Dropped items count as handled; the unwritten ones are retried."""
        try:
            with self._session_factory() as db:
                for item in batch:
                    _add_item(db, item)
                db.commit()
            return [], 0
        except SQLAlchemyError as exc:
            if not isinstance(exc, IntegrityError):
                # The database itself is unavailable or unhappy: nothing was committed
                # (one transaction), so the whole batch is retried.
                logger.exception("Writing %d event(s) failed; will retry", len(batch))
                return batch, 0
            logger.warning("A batch hit an integrity error (camera deleted?); retrying item by item")
        except Exception:
            # Not a database problem: a bad item (a bug). Retrying it would block everything
            # behind it forever, so isolate it below instead.
            logger.exception("Unexpected failure writing a batch; retrying item by item")

        # At least one item can never be written. Find it without losing the rest.
        unwritable = 0
        for index, item in enumerate(batch):
            try:
                with self._session_factory() as db:
                    _add_item(db, item)
                    db.commit()
            except SQLAlchemyError as exc:
                if not isinstance(exc, IntegrityError):
                    logger.exception("Database failure mid-batch; will retry the rest")
                    return batch[index:], unwritable
                logger.warning("Dropped an unwritable %s (its camera no longer exists)", type(item).__name__)
                self._count_dropped(1)
                unwritable += 1
            except Exception:
                logger.exception("Dropped a %s that could not be written", type(item).__name__)
                self._count_dropped(1)
                unwritable += 1
        return [], unwritable


def close_dangling_sessions(session_factory: Callable = SessionLocal) -> int:
    """Startup step. A camera whose most recent uptime event says it was running, when the
    backend was not running, was interrupted (crash, kill, power loss) and never got its
    `tracking_stopped`. Close it — stamped at the camera's last event of any kind, a
    conservative bound so uptime is under- rather than over-stated."""
    closed = 0
    with session_factory() as db:
        latest = db.scalars(
            select(Event)
            .where(Event.event_type.in_(UPTIME_EVENT_TYPES))
            .distinct(Event.camera_id)
            .order_by(Event.camera_id, Event.occurred_at.desc())
        ).all()
        for last_uptime in latest:
            if last_uptime.event_type not in UPTIME_RUNNING_TYPES and last_uptime.event_type != TRACKING_RECONNECTING:
                continue
            last_event_at = db.scalar(select(func.max(Event.occurred_at)).where(Event.camera_id == last_uptime.camera_id))
            db.add(
                Event(
                    camera_id=last_uptime.camera_id,
                    # A microsecond after it, so the closing event always sorts *after* the
                    # one it closes: with an identical timestamp the two would tie, and
                    # "the latest uptime event" (used here and by analytics) would be ambiguous.
                    occurred_at=last_event_at + timedelta(microseconds=1),
                    event_type=TRACKING_STOPPED,
                    value="Backend restarted",
                )
            )
            closed += 1
        db.commit()
    return closed


event_recorder = EventRecorder()
