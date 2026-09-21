"""Historical analytics, computed live from the `events` table (and `heatmap_snapshots`).

Nothing here is stored or pre-aggregated: totals and trends are indexed SQL over events, so
there is one source of truth and nothing to fall out of sync.

Time zones are handled by PostgreSQL (`timezone()`, `date_trunc`, `generate_series`), not
Python: correct DST/offset behavior with no Python tz database (on Windows that would need
the `tzdata` package). A repeated DST hour merges into a single hourly bucket.

The uptime helpers turn tracking_started/stopped/... events into "tracked" intervals, which
is what lets a chart say "not running" for a bucket instead of drawing it as zero traffic.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional

import numpy as np
from sqlalchemy import and_, func, select, text
from sqlalchemy.orm import Session

from app.events import (
    LINE_CROSSED,
    READ,
    UPTIME_EVENT_TYPES,
    UPTIME_RUNNING_TYPES,
    ZONE_ENTERED,
    ZONE_EXITED,
    hour_start,
)
from app.heatmap import decode_grid
from app.models import Event, HeatmapSnapshot

MAX_BUCKETS = 1000
BUCKET_UNITS = {"hour": "1 hour", "day": "1 day"}


class AnalyticsInputError(ValueError):
    """The caller asked for something invalid (unknown time zone, too many buckets...)."""


Interval = tuple[datetime, datetime]


# -- uptime ----------------------------------------------------------------------------


def tracked_intervals(
    prior_type: Optional[str],
    events: Iterable[tuple[datetime, str]],
    since: datetime,
    end: datetime,
) -> list[Interval]:
    """When one camera was tracking, within [since, end).

    `prior_type` is the camera's last uptime event *before* `since` (None if there was
    none): if it says running, tracking was already under way at `since`. `events` are the
    camera's uptime events from `since` on, oldest first. A start with no matching stop
    counts up to `end` — the caller passes min(range end, now), and startup closes sessions
    a crash left dangling (app.events.close_dangling_sessions).
    """
    intervals: list[Interval] = []
    open_at: Optional[datetime] = since if prior_type in UPTIME_RUNNING_TYPES else None
    for occurred_at, event_type in events:
        if event_type in UPTIME_RUNNING_TYPES:
            if open_at is None:
                open_at = occurred_at
        elif open_at is not None:
            intervals.append((open_at, occurred_at))
            open_at = None
    if open_at is not None and end > open_at:
        intervals.append((open_at, end))
    return [(s, e) for s, e in intervals if e > s]


def overlap_seconds(intervals: Iterable[Interval], start: datetime, end: datetime) -> float:
    total = 0.0
    for interval_start, interval_end in intervals:
        overlap = (min(interval_end, end) - max(interval_start, start)).total_seconds()
        if overlap > 0:
            total += overlap
    return total


def uptime_intervals(
    db: Session, camera_id: Optional[uuid.UUID], since: datetime, until: datetime, now: datetime
) -> list[Interval]:
    """Every camera's tracked intervals in the range (one camera, or all of them),
    flattened: summing their overlap with a bucket gives camera-seconds tracked."""
    end = min(until, now)
    if end <= since:
        return []

    camera_filter = [Event.camera_id == camera_id] if camera_id else []
    prior = db.scalars(
        select(Event)
        .where(Event.event_type.in_(UPTIME_EVENT_TYPES), Event.occurred_at < since, *camera_filter)
        .distinct(Event.camera_id)
        .order_by(Event.camera_id, Event.occurred_at.desc())
    ).all()
    prior_type_by_camera = {event.camera_id: event.event_type for event in prior}

    in_range = db.execute(
        select(Event.camera_id, Event.occurred_at, Event.event_type)
        .where(Event.event_type.in_(UPTIME_EVENT_TYPES), Event.occurred_at >= since, Event.occurred_at < end, *camera_filter)
        .order_by(Event.occurred_at, Event.id)
    ).all()
    events_by_camera: dict[uuid.UUID, list[tuple[datetime, str]]] = {}
    for cam, occurred_at, event_type in in_range:
        events_by_camera.setdefault(cam, []).append((occurred_at, event_type))

    intervals: list[Interval] = []
    for cam in set(prior_type_by_camera) | set(events_by_camera):
        intervals += tracked_intervals(prior_type_by_camera.get(cam), events_by_camera.get(cam, []), since, end)
    return intervals


# -- time zones --------------------------------------------------------------------------


def validate_timezone(db: Session, tz: str) -> str:
    known = db.scalar(text("SELECT EXISTS (SELECT 1 FROM pg_timezone_names WHERE name = :tz)"), {"tz": tz})
    if not known:
        raise AnalyticsInputError(f"Unknown time zone: {tz!r}")
    return tz


# -- summary -----------------------------------------------------------------------------


def _count_where(*conditions):
    return func.count().filter(and_(*conditions))


def _crossing_counts():
    e = Event
    return [
        _count_where(e.event_type == LINE_CROSSED, e.category == "person", e.direction == "in").label("people_in"),
        _count_where(e.event_type == LINE_CROSSED, e.category == "person", e.direction == "out").label("people_out"),
        _count_where(e.event_type == LINE_CROSSED, e.category == "vehicle", e.direction == "in").label("vehicle_in"),
        _count_where(e.event_type == LINE_CROSSED, e.category == "vehicle", e.direction == "out").label("vehicle_out"),
    ]


def _range_filters(camera_id: Optional[uuid.UUID], since: datetime, until: datetime) -> list:
    filters = [Event.occurred_at >= since, Event.occurred_at < until]
    if camera_id:
        filters.append(Event.camera_id == camera_id)
    return filters


def summary(db: Session, camera_id: Optional[uuid.UUID], since: datetime, until: datetime, now: datetime) -> dict:
    e = Event
    filters = _range_filters(camera_id, since, until)

    totals = db.execute(select(*_crossing_counts()).where(*filters)).one()

    lines = db.execute(
        select(e.subject_id, e.subject_name, *_crossing_counts())
        .where(*filters, e.event_type == LINE_CROSSED)
        .group_by(e.subject_id, e.subject_name)
        .order_by(e.subject_name)
    ).all()

    zones = db.execute(
        select(
            e.subject_id,
            e.subject_name,
            _count_where(e.event_type == ZONE_ENTERED).label("entered"),
            _count_where(e.event_type == ZONE_EXITED).label("exited"),
        )
        .where(*filters, e.event_type.in_([ZONE_ENTERED, ZONE_EXITED]))
        .group_by(e.subject_id, e.subject_name)
        .order_by(e.subject_name)
    ).all()

    reads = dict(
        db.execute(select(e.category, func.count()).where(*filters, e.event_type == READ).group_by(e.category)).all()
    )

    tracked = sum(
        (end - start).total_seconds() for start, end in uptime_intervals(db, camera_id, since, until, now)
    )

    return {
        "since": since,
        "until": until,
        "people_in": totals.people_in,
        "people_out": totals.people_out,
        "vehicle_in": totals.vehicle_in,
        "vehicle_out": totals.vehicle_out,
        "lines": [
            {
                "line_id": row.subject_id,
                "name": row.subject_name,
                "people_in": row.people_in,
                "people_out": row.people_out,
                "vehicle_in": row.vehicle_in,
                "vehicle_out": row.vehicle_out,
            }
            for row in lines
        ],
        "zones": [
            {"zone_id": row.subject_id, "name": row.subject_name, "entered": row.entered, "exited": row.exited}
            for row in zones
        ],
        "reads": {"qr": reads.get("qr", 0), "barcode": reads.get("barcode", 0), "ocr": reads.get("ocr", 0)},
        "tracked_seconds": tracked,
    }


# -- time series -------------------------------------------------------------------------

_BUCKETS_SQL = text(
    """
    SELECT gs AS local_start,
           (gs AT TIME ZONE :tz) AS start_utc,
           ((gs + CAST(:step AS interval)) AT TIME ZONE :tz) AS end_utc
    FROM generate_series(
        date_trunc(:unit, CAST(:since AS timestamptz) AT TIME ZONE :tz),
        (CAST(:until AS timestamptz) AT TIME ZONE :tz) - interval '1 microsecond',
        CAST(:step AS interval)
    ) AS gs
    ORDER BY gs
    """
)


def timeseries(
    db: Session,
    camera_id: Optional[uuid.UUID],
    since: datetime,
    until: datetime,
    bucket: str,
    tz: str,
    now: datetime,
) -> dict:
    """Zero-filled buckets across [since, until), each with its counts and how many
    camera-seconds were actually being tracked, so "0 people" can be told apart from
    "not running"."""
    if bucket not in BUCKET_UNITS:
        raise AnalyticsInputError(f"bucket must be one of {sorted(BUCKET_UNITS)}")
    validate_timezone(db, tz)

    buckets = db.execute(
        _BUCKETS_SQL, {"tz": tz, "unit": bucket, "step": BUCKET_UNITS[bucket], "since": since, "until": until}
    ).all()
    if len(buckets) > MAX_BUCKETS:
        raise AnalyticsInputError(
            f"That range makes {len(buckets)} {bucket} buckets; the limit is {MAX_BUCKETS}. Use a shorter range or day buckets."
        )

    e = Event
    local_bucket = func.date_trunc(bucket, func.timezone(tz, e.occurred_at)).label("local_start")
    rows = db.execute(
        select(
            local_bucket,
            *_crossing_counts(),
            _count_where(e.event_type == ZONE_ENTERED).label("zone_entered"),
            _count_where(e.event_type == ZONE_EXITED).label("zone_exited"),
            _count_where(e.event_type == READ).label("reads"),
        )
        .where(*_range_filters(camera_id, since, until))
        # Ordinal, not the expression: repeating a parametrised date_trunc(...) in GROUP BY
        # gets fresh bind parameters, which PostgreSQL then refuses to treat as the same.
        .group_by(text("1"))
    ).all()
    counts_by_bucket = {row.local_start: row for row in rows}

    intervals = uptime_intervals(db, camera_id, since, until, now)

    points = []
    for local_start, start_utc, end_utc in buckets:
        if end_utc <= start_utc:
            # A local hour that doesn't exist: on the day the clocks go forward, 02:00 is
            # skipped, and PostgreSQL maps that phantom bucket onto a zero-length span.
            continue
        row = counts_by_bucket.get(local_start)
        points.append(
            {
                "start": start_utc,
                "end": end_utc,
                "people_in": row.people_in if row else 0,
                "people_out": row.people_out if row else 0,
                "vehicle_in": row.vehicle_in if row else 0,
                "vehicle_out": row.vehicle_out if row else 0,
                "zone_entered": row.zone_entered if row else 0,
                "zone_exited": row.zone_exited if row else 0,
                "reads": row.reads if row else 0,
                "tracked_seconds": overlap_seconds(intervals, max(start_utc, since), min(end_utc, until)),
            }
        )
    return {"bucket": bucket, "tz": tz, "since": since, "until": until, "points": points}


# -- heatmap -----------------------------------------------------------------------------


@dataclass
class HeatSum:
    grid: np.ndarray
    frame_width: int
    frame_height: int
    samples: int
    first_period: datetime
    last_period: datetime
    ignored_samples: int  # from snapshots with a different grid size than the one shown


def heat_sum(db: Session, camera_id: uuid.UUID, since: datetime, until: datetime) -> Optional[HeatSum]:
    """The camera's stored heat over the range, summed. Snapshots are hourly, so the hour
    containing `since` is included whole — the range's edges are only hour-accurate.

    If the camera's resolution changed within the range, snapshots have different grid
    sizes and can't be added; the size with the most samples is shown and the rest are
    reported as `ignored_samples`.
    """
    rows = db.scalars(
        select(HeatmapSnapshot)
        .where(
            HeatmapSnapshot.camera_id == camera_id,
            HeatmapSnapshot.period_start >= hour_start(since),
            HeatmapSnapshot.period_start < until,
        )
        .order_by(HeatmapSnapshot.period_start)
    ).all()
    if not rows:
        return None

    samples_by_grid: dict[tuple[int, int], int] = {}
    for row in rows:
        key = (row.grid_width, row.grid_height)
        samples_by_grid[key] = samples_by_grid.get(key, 0) + row.sample_count
    chosen = max(samples_by_grid, key=samples_by_grid.get)
    used = [row for row in rows if (row.grid_width, row.grid_height) == chosen]

    grid = np.zeros((chosen[1], chosen[0]), dtype=np.uint64)
    for row in used:
        grid += decode_grid(row.cells, row.grid_width, row.grid_height)

    return HeatSum(
        grid=grid,
        frame_width=used[-1].frame_width,
        frame_height=used[-1].frame_height,
        samples=samples_by_grid[chosen],
        first_period=used[0].period_start,
        last_period=used[-1].period_start,
        ignored_samples=sum(samples_by_grid.values()) - samples_by_grid[chosen],
    )


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
