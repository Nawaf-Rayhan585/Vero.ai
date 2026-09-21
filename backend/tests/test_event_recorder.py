"""The event write path: batching, never blocking the producer, surviving database trouble,
and dropping only what can never be written. Real PostgreSQL throughout; the failure modes
are produced by wrapping the real session factory, not by faking the database.
"""
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from app.database import SessionLocal
from app.events import EventRecorder, HeatDelta, NewEvent, hour_start
from app.heatmap import decode_grid
from app.models import Event, HeatmapSnapshot

NOW = datetime(2026, 3, 10, 14, 5, 30, tzinfo=timezone.utc)


def _create_camera(client, name="Front door") -> uuid.UUID:
    response = client.post("/cameras", json={"name": name, "rtsp_url": "rtsp://192.0.2.10:554/stream1"})
    return uuid.UUID(response.json()["id"])


def _event(camera_id, **overrides) -> NewEvent:
    fields = dict(
        camera_id=camera_id,
        event_type="line_crossed",
        occurred_at=NOW,
        category="person",
        direction="in",
        subject_id=uuid.uuid4(),
        subject_name="Entrance",
    )
    fields.update(overrides)
    return NewEvent(**fields)


def _heat(camera_id, cells, period=None, samples=None) -> HeatDelta:
    grid = np.zeros((40, 80), dtype=np.uint32)
    for (row, col), count in cells.items():
        grid[row, col] = count
    return HeatDelta(
        camera_id=camera_id,
        period_start=period or hour_start(NOW),
        frame_width=800,
        frame_height=400,
        grid=grid,
        samples=samples if samples is not None else int(grid.sum()),
    )


def _count(db_session, model) -> int:
    db_session.expire_all()
    return db_session.scalar(select(func.count()).select_from(model))


@pytest.fixture
def recorder():
    recorder = EventRecorder(retry_backoff=(0.01,))
    yield recorder
    recorder.stop(timeout=5)


class TestPersisting:
    def test_an_event_is_written_with_every_field(self, client, db_session, recorder):
        camera_id = _create_camera(client)
        line_id = uuid.uuid4()

        recorder.record(
            NewEvent(
                camera_id=camera_id,
                event_type="line_crossed",
                occurred_at=NOW,
                category="vehicle",
                direction="out",
                subject_id=line_id,
                subject_name="Gate",
                value=None,
                detail="x",
            )
        )
        assert recorder.flush()

        (row,) = db_session.scalars(select(Event)).all()
        assert (row.camera_id, row.event_type, row.category, row.direction) == (camera_id, "line_crossed", "vehicle", "out")
        assert (row.subject_id, row.subject_name, row.detail) == (line_id, "Gate", "x")
        assert row.occurred_at == NOW

    def test_many_events_are_written_in_batches(self, client, db_session):
        camera_id = _create_camera(client)
        recorder = EventRecorder(batch_size=50)
        try:
            for _ in range(430):
                recorder.record(_event(camera_id))
            assert recorder.flush()
        finally:
            recorder.stop(timeout=5)

        assert _count(db_session, Event) == 430
        assert recorder.written == 430 and recorder.dropped == 0

    def test_it_starts_itself_on_first_use(self, client, db_session, recorder):
        camera_id = _create_camera(client)
        assert recorder._thread is None

        recorder.record(_event(camera_id))

        assert recorder._thread is not None and recorder._thread.is_alive()
        assert recorder.flush()

    def test_recording_is_thread_safe(self, client, db_session, recorder):
        camera_id = _create_camera(client)

        def produce():
            for _ in range(100):
                recorder.record(_event(camera_id))

        threads = [threading.Thread(target=produce) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert recorder.flush()

        assert _count(db_session, Event) == 600

    def test_stop_drains_whatever_is_queued(self, client, db_session):
        camera_id = _create_camera(client)
        recorder = EventRecorder()
        for _ in range(60):
            recorder.record(_event(camera_id))

        recorder.stop(timeout=10)  # no flush() first

        assert _count(db_session, Event) == 60

    def test_it_can_be_restarted_after_stop(self, client, db_session):
        camera_id = _create_camera(client)
        recorder = EventRecorder()
        recorder.record(_event(camera_id))
        recorder.stop(timeout=5)

        recorder.record(_event(camera_id))
        assert recorder.flush()
        recorder.stop(timeout=5)

        assert _count(db_session, Event) == 2


class TestNeverBlocksOrRaises:
    def test_a_full_queue_drops_the_new_event_instead_of_blocking(self, client, db_session):
        camera_id = _create_camera(client)
        release = threading.Event()
        picked_up = threading.Event()

        def blocked_factory():
            picked_up.set()
            release.wait(10)
            return SessionLocal()

        recorder = EventRecorder(session_factory=blocked_factory, max_queue=3)
        try:
            recorder.record(_event(camera_id))  # the writer takes this one and blocks on it
            assert picked_up.wait(5)
            for _ in range(3):
                recorder.record(_event(camera_id))  # fills the queue

            started = time.monotonic()
            recorder.record(_event(camera_id))  # one too many
            assert time.monotonic() - started < 0.5  # returned at once

            assert recorder.dropped == 1
        finally:
            release.set()
            recorder.flush()
            recorder.stop(timeout=5)

        assert _count(db_session, Event) == 4  # the dropped one is the only loss

    def test_record_never_raises_even_when_the_writer_cannot_start(self, monkeypatch):
        recorder = EventRecorder()
        monkeypatch.setattr(recorder, "_ensure_started", lambda: (_ for _ in ()).throw(RuntimeError("no threads")))

        recorder.record(NewEvent(camera_id=uuid.uuid4(), event_type="line_crossed"))  # must not raise


class TestDatabaseTrouble:
    def test_a_database_outage_is_retried_until_it_recovers(self, client, db_session):
        camera_id = _create_camera(client)
        calls = {"n": 0}

        def flaky_factory():
            calls["n"] += 1
            if calls["n"] <= 3:
                raise OperationalError("INSERT", {}, Exception("database is down"))
            return SessionLocal()

        recorder = EventRecorder(session_factory=flaky_factory, retry_backoff=(0.01,))
        try:
            for _ in range(5):
                recorder.record(_event(camera_id))
            assert recorder.flush(timeout=10)
        finally:
            recorder.stop(timeout=5)

        assert calls["n"] > 3
        assert _count(db_session, Event) == 5  # nothing lost, nothing duplicated
        assert recorder.dropped == 0

    def test_a_failed_batch_is_retried_before_newer_events_so_order_survives(self, client, db_session):
        camera_id = _create_camera(client)
        calls = {"n": 0}

        def flaky_factory():
            calls["n"] += 1
            if calls["n"] == 1:
                raise OperationalError("INSERT", {}, Exception("blip"))
            return SessionLocal()

        recorder = EventRecorder(session_factory=flaky_factory, retry_backoff=(0.01,), batch_size=2)
        try:
            for i in range(6):
                recorder.record(_event(camera_id, value=str(i), occurred_at=NOW + timedelta(seconds=i)))
            assert recorder.flush(timeout=10)
        finally:
            recorder.stop(timeout=5)

        db_session.expire_all()
        values = [e.value for e in db_session.scalars(select(Event).order_by(Event.occurred_at))]
        assert values == ["0", "1", "2", "3", "4", "5"]

    def test_shutting_down_with_the_database_down_gives_up_instead_of_hanging(self):
        def always_down():
            raise OperationalError("INSERT", {}, Exception("database is down"))

        recorder = EventRecorder(session_factory=always_down, retry_backoff=(0.01,))
        for _ in range(3):
            recorder.record(NewEvent(camera_id=uuid.uuid4(), event_type="line_crossed"))

        started = time.monotonic()
        recorder.stop(timeout=10)

        assert time.monotonic() - started < 5
        assert recorder.dropped == 3


class TestUnwritableItems:
    def test_events_for_a_deleted_camera_are_dropped_and_the_rest_still_written(self, client, db_session, recorder):
        alive = _create_camera(client, "Alive")
        gone = uuid.uuid4()  # a camera that does not exist (e.g. deleted while tracking)

        # One batch containing both kinds.
        recorder.record(_event(alive, value="a"))
        recorder.record(_event(gone, value="lost-1"))
        recorder.record(_event(alive, value="b"))
        recorder.record(_event(gone, value="lost-2"))
        recorder.record(_event(alive, value="c"))
        assert recorder.flush()

        db_session.expire_all()
        assert sorted(e.value for e in db_session.scalars(select(Event))) == ["a", "b", "c"]
        assert recorder.dropped == 2
        assert recorder.written == 3

    def test_a_poison_item_is_dropped_without_blocking_the_queue(self, client, db_session, recorder):
        camera_id = _create_camera(client)

        recorder.record(_event(camera_id, value="before"))
        recorder.record(object())  # not an event or a heat delta: a bug somewhere upstream
        recorder.record(_event(camera_id, value="after"))
        assert recorder.flush(timeout=10)

        db_session.expire_all()
        assert sorted(e.value for e in db_session.scalars(select(Event))) == ["after", "before"]
        assert recorder.dropped == 1

    def test_heat_for_a_deleted_camera_is_dropped(self, client, db_session, recorder):
        recorder.record(_heat(uuid.uuid4(), {(5, 5): 3}))
        assert recorder.flush()

        assert _count(db_session, HeatmapSnapshot) == 0
        assert recorder.dropped == 1


class TestHeatSnapshots:
    def test_a_heat_delta_becomes_one_hourly_snapshot(self, client, db_session, recorder):
        camera_id = _create_camera(client)

        recorder.record(_heat(camera_id, {(10, 20): 4, (11, 21): 2}))
        assert recorder.flush()

        (snapshot,) = db_session.scalars(select(HeatmapSnapshot)).all()
        assert snapshot.camera_id == camera_id
        assert snapshot.period_start == hour_start(NOW)
        assert (snapshot.frame_width, snapshot.frame_height) == (800, 400)
        assert (snapshot.grid_width, snapshot.grid_height) == (80, 40)
        assert snapshot.sample_count == 6
        grid = decode_grid(snapshot.cells, 80, 40)
        assert grid[10, 20] == 4 and grid[11, 21] == 2 and grid.sum() == 6

    def test_a_second_delta_in_the_same_hour_is_merged_into_the_same_row(self, client, db_session, recorder):
        camera_id = _create_camera(client)

        recorder.record(_heat(camera_id, {(10, 20): 4}))
        recorder.record(_heat(camera_id, {(10, 20): 3, (0, 0): 1}))
        assert recorder.flush()

        (snapshot,) = db_session.scalars(select(HeatmapSnapshot)).all()
        grid = decode_grid(snapshot.cells, 80, 40)
        assert grid[10, 20] == 7 and grid[0, 0] == 1
        assert snapshot.sample_count == 8

    def test_a_different_hour_is_a_separate_row(self, client, db_session, recorder):
        camera_id = _create_camera(client)

        recorder.record(_heat(camera_id, {(1, 1): 1}, period=hour_start(NOW)))
        recorder.record(_heat(camera_id, {(1, 1): 1}, period=hour_start(NOW) + timedelta(hours=1)))
        assert recorder.flush()

        assert _count(db_session, HeatmapSnapshot) == 2

    def test_a_different_camera_is_a_separate_row(self, client, db_session, recorder):
        recorder.record(_heat(_create_camera(client, "A"), {(1, 1): 1}))
        recorder.record(_heat(_create_camera(client, "B"), {(1, 1): 1}))
        assert recorder.flush()

        assert _count(db_session, HeatmapSnapshot) == 2

    def test_a_snapshot_is_small(self, client, db_session, recorder):
        camera_id = _create_camera(client)
        recorder.record(_heat(camera_id, {(r, c): 5 for r in range(10, 30) for c in range(20, 60)}))
        assert recorder.flush()

        (snapshot,) = db_session.scalars(select(HeatmapSnapshot)).all()
        assert len(snapshot.cells) < 4000  # an 80x40 grid of uint32 is 12,800 bytes raw

    def test_deleting_a_camera_deletes_its_events_and_snapshots(self, client, db_session, recorder):
        camera_id = _create_camera(client)
        recorder.record(_event(camera_id))
        recorder.record(_heat(camera_id, {(1, 1): 1}))
        assert recorder.flush()
        assert _count(db_session, Event) == 1 and _count(db_session, HeatmapSnapshot) == 1

        assert client.delete(f"/cameras/{camera_id}").status_code == 204

        assert _count(db_session, Event) == 0
        assert _count(db_session, HeatmapSnapshot) == 0
