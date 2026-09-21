"""Event generation inside TrackingSession. Direct tests of the per-frame methods with
synthetic positions and a fake recorder (no video, no model, no database — same style as
test_tracking_counting.py), then real end-to-end runs through the actual capture loop,
YOLO/ByteTrack, the recorder, PostgreSQL and the HTTP API.
"""
import time
import uuid
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from app import tracking
from app.counting import LineConfig, Point
from app.events import EventRecorder, HeatDelta, NewEvent, event_recorder, hour_start
from app.heatmap import HeatmapAccumulator
from app.scanning import SIGHTING_GAP_SECONDS, ReadRegistry
from app.tracking import HEAT_FLUSH_INTERVAL_SECONDS, ZONE_LOST_GRACE_FRAMES, TrackingSession
from app.zones import ZoneConfig


class FakeRecorder:
    def __init__(self):
        self.items = []

    def record(self, item):
        self.items.append(item)

    @property
    def events(self):
        return [i for i in self.items if isinstance(i, NewEvent)]

    @property
    def heat(self):
        return [i for i in self.items if isinstance(i, HeatDelta)]

    def types(self):
        return [e.event_type for e in self.events]


def _line(x=0.5) -> LineConfig:
    # Bottom-to-top, so left-to-right movement is "in" (see test_counting.py).
    return LineConfig(id=uuid.uuid4(), name="Gate", x1=x, y1=1.0, x2=x, y2=0.0)


def _zone(name="Checkout", left=0.0, right=0.5) -> ZoneConfig:
    points = ((left, 0.0), (right, 0.0), (right, 1.0), (left, 1.0))
    return ZoneConfig(id=uuid.uuid4(), name=name, points=tuple(Point(x, y) for x, y in points))


def _session(recorder, lines=None, zones=None, modules=None) -> TrackingSession:
    session = TrackingSession(uuid.uuid4(), "unused://", None, None, lines, zones, modules, recorder)
    session._resolved_lines = [line.to_pixels(1000, 1000) for line in lines or []]
    session._resolved_zones = [zone.to_pixels(1000, 1000) for zone in zones or []]
    return session


class TestLineCrossingEvents:
    def test_a_crossing_emits_an_event_with_line_direction_and_category(self):
        recorder, line = FakeRecorder(), _line()
        session = _session(recorder, lines=[line])

        session._update_counts({1: Point(400, 500)})
        session._update_counts({1: Point(600, 500)})

        (event,) = recorder.events
        assert event.event_type == "line_crossed"
        assert (event.category, event.direction) == ("person", "in")
        assert (event.subject_id, event.subject_name) == (line.id, "Gate")
        assert event.camera_id == session.camera_id
        assert event.occurred_at.tzinfo is not None
        assert abs((datetime.now(timezone.utc) - event.occurred_at).total_seconds()) < 5

    def test_crossing_back_emits_out(self):
        recorder = FakeRecorder()
        session = _session(recorder, lines=[_line()])

        for x in (400, 600, 400):
            session._update_counts({1: Point(x, 500)})

        assert [(e.category, e.direction) for e in recorder.events] == [("person", "in"), ("person", "out")]

    def test_a_vehicle_crossing_is_categorised_as_a_vehicle(self):
        recorder = FakeRecorder()
        session = _session(recorder, lines=[_line()], modules=["vehicles"])

        session._update_counts({7: Point(400, 500)}, "vehicle")
        session._update_counts({7: Point(600, 500)}, "vehicle")

        (event,) = recorder.events
        assert (event.category, event.direction) == ("vehicle", "in")

    def test_every_line_crossed_gets_its_own_event(self):
        recorder = FakeRecorder()
        a, b = _line(0.3), _line(0.7)
        session = _session(recorder, lines=[a, b])

        session._update_counts({1: Point(200, 500)})
        session._update_counts({1: Point(800, 500)})  # crosses both lines in one step

        assert {e.subject_id for e in recorder.events} == {a.id, b.id}

    def test_no_crossing_no_event(self):
        recorder = FakeRecorder()
        session = _session(recorder, lines=[_line()])

        for x in (100, 150, 200):
            session._update_counts({1: Point(x, 500)})

        assert recorder.events == []

    def test_a_session_without_a_recorder_still_counts_and_does_not_crash(self):
        session = _session(None, lines=[_line()])

        session._update_counts({1: Point(400, 500)})
        session._update_counts({1: Point(600, 500)})

        assert session.snapshot().line_counts[0]["in_count"] == 1


class TestZoneEvents:
    def test_walking_into_and_out_of_a_zone_emits_entered_then_exited(self):
        recorder, zone = FakeRecorder(), _zone()
        session = _session(recorder, zones=[zone])

        session._update_zones({1: Point(800, 500)})  # outside
        session._update_zones({1: Point(300, 500)})  # in
        session._update_zones({1: Point(250, 500)})  # still in: nothing new
        session._update_zones({1: Point(700, 500)})  # out

        assert recorder.types() == ["zone_entered", "zone_exited"]
        entered = recorder.events[0]
        assert (entered.category, entered.subject_id, entered.subject_name) == ("person", zone.id, "Checkout")

    def test_someone_first_seen_inside_a_zone_counts_as_entered(self):
        recorder = FakeRecorder()
        session = _session(recorder, zones=[_zone()])

        session._update_zones({1: Point(300, 500)})

        assert recorder.types() == ["zone_entered"]

    def test_overlapping_zones_each_get_their_own_event(self):
        recorder = FakeRecorder()
        a, b = _zone("A", 0.0, 0.6), _zone("B", 0.4, 1.0)
        session = _session(recorder, zones=[a, b])

        session._update_zones({1: Point(500, 500)})  # inside both

        assert {e.subject_id for e in recorder.events} == {a.id, b.id}

    def test_each_person_is_tracked_separately(self):
        recorder = FakeRecorder()
        session = _session(recorder, zones=[_zone()])

        session._update_zones({1: Point(300, 500), 2: Point(800, 500)})
        session._update_zones({1: Point(300, 500), 2: Point(200, 500)})

        assert recorder.types() == ["zone_entered", "zone_entered"]

    def test_a_brief_disappearance_inside_a_zone_does_not_re_emit_entered(self):
        recorder = FakeRecorder()
        session = _session(recorder, zones=[_zone()])
        session._update_zones({1: Point(300, 500)})

        for _ in range(ZONE_LOST_GRACE_FRAMES - 1):  # occluded for a while, but not too long
            session._update_zones({})
        session._update_zones({1: Point(300, 500)})  # back, still inside

        assert recorder.types() == ["zone_entered"]  # no exit, no second entry

    def test_someone_lost_inside_a_zone_gets_an_exit_once_the_grace_period_passes(self):
        recorder = FakeRecorder()
        session = _session(recorder, zones=[_zone()])
        session._update_zones({1: Point(300, 500)})

        for _ in range(ZONE_LOST_GRACE_FRAMES):
            session._update_zones({})
        assert recorder.types() == ["zone_entered"]  # still within the grace period

        session._update_zones({})  # one frame beyond it
        assert recorder.types() == ["zone_entered", "zone_exited"]

    def test_the_lost_exit_is_emitted_only_once(self):
        recorder = FakeRecorder()
        session = _session(recorder, zones=[_zone()])
        session._update_zones({1: Point(300, 500)})

        for _ in range(ZONE_LOST_GRACE_FRAMES + 20):
            session._update_zones({})

        assert recorder.types() == ["zone_entered", "zone_exited"]

    def test_coming_back_after_being_lost_is_a_new_entry(self):
        recorder = FakeRecorder()
        session = _session(recorder, zones=[_zone()])
        session._update_zones({1: Point(300, 500)})
        for _ in range(ZONE_LOST_GRACE_FRAMES + 1):
            session._update_zones({})

        session._update_zones({1: Point(300, 500)})

        assert recorder.types() == ["zone_entered", "zone_exited", "zone_entered"]

    def test_being_lost_while_inside_two_zones_exits_both(self):
        recorder = FakeRecorder()
        a, b = _zone("A", 0.0, 0.6), _zone("B", 0.4, 1.0)
        session = _session(recorder, zones=[a, b])
        session._update_zones({1: Point(500, 500)})
        recorder.items.clear()

        for _ in range(ZONE_LOST_GRACE_FRAMES + 1):
            session._update_zones({})

        assert sorted(e.subject_name for e in recorder.events) == ["A", "B"]
        assert set(recorder.types()) == {"zone_exited"}

    def test_a_person_lost_while_outside_every_zone_emits_nothing(self):
        recorder = FakeRecorder()
        session = _session(recorder, zones=[_zone()])
        session._update_zones({1: Point(800, 500)})

        for _ in range(ZONE_LOST_GRACE_FRAMES + 5):
            session._update_zones({})

        assert recorder.events == []

    def test_lost_tracks_are_forgotten_so_memory_does_not_grow(self):
        session = _session(FakeRecorder(), zones=[_zone()])
        for track_id in range(200):
            session._update_zones({track_id: Point(300, 500)})
            session._update_zones({})
        for _ in range(ZONE_LOST_GRACE_FRAMES + 2):
            session._update_zones({})

        assert session._zone_membership == {}

    def test_the_live_counts_are_unchanged_by_event_generation(self):
        session = _session(FakeRecorder(), zones=[_zone("Left", 0.0, 0.5)])

        session._update_zones({1: Point(300, 500), 2: Point(200, 500), 3: Point(800, 500)})

        assert session.snapshot().zone_counts[0]["count"] == 2


class TestReadEvents:
    def _session_with_clock(self, recorder):
        clock = {"now": 100.0}
        session = _session(recorder, modules=["qr"])
        session._reads = ReadRegistry(clock=lambda: clock["now"], on_new_sighting=session._on_new_read)
        return session, clock

    def test_a_new_read_emits_one_event_with_its_kind_value_and_detail(self):
        recorder = FakeRecorder()
        session, _clock = self._session_with_clock(recorder)

        session._reads.record("qr", "https://vero.ai/t/42", "QR Code", [(0.0, 0.0)] * 4)

        (event,) = recorder.events
        assert event.event_type == "read"
        assert (event.category, event.value, event.detail) == ("qr", "https://vero.ai/t/42", "QR Code")

    def test_a_code_that_stays_in_view_is_one_event_not_one_per_frame(self):
        recorder = FakeRecorder()
        session, clock = self._session_with_clock(recorder)

        for _ in range(300):  # a minute at 5 fps
            session._reads.record("qr", "abc", "QR Code", [(0.0, 0.0)] * 4)
            clock["now"] += 0.2

        assert len(recorder.events) == 1

    def test_seeing_it_again_after_the_gap_is_a_new_event(self):
        recorder = FakeRecorder()
        session, clock = self._session_with_clock(recorder)
        session._reads.record("qr", "abc", "QR Code", [(0.0, 0.0)] * 4)

        clock["now"] += SIGHTING_GAP_SECONDS + 1
        session._reads.record("qr", "abc", "QR Code", [(0.0, 0.0)] * 4)

        assert len(recorder.events) == 2

    def test_different_values_are_different_events(self):
        recorder = FakeRecorder()
        session, _clock = self._session_with_clock(recorder)

        session._reads.record("qr", "one", "QR Code", [(0.0, 0.0)] * 4)
        session._reads.record("barcode", "one", "Code 128", [(0.0, 0.0)] * 4)
        session._reads.record("qr", "two", "QR Code", [(0.0, 0.0)] * 4)

        assert [(e.category, e.value) for e in recorder.events] == [("qr", "one"), ("barcode", "one"), ("qr", "two")]


class TestUptimeEvents:
    def test_the_reconnect_loop_emits_reconnecting_then_resumed(self, monkeypatch):
        recorder = FakeRecorder()
        session = _session(recorder)
        monkeypatch.setattr(tracking, "RECONNECT_INTERVAL_SECONDS", 0.01)
        monkeypatch.setattr(tracking, "_open_capture", lambda url: object())

        assert session._reconnect_loop() is not None

        assert recorder.types() == ["tracking_reconnecting", "tracking_resumed"]

    def test_giving_up_emits_reconnecting_and_no_resume(self, monkeypatch):
        recorder = FakeRecorder()
        session = _session(recorder)
        monkeypatch.setattr(tracking, "RECONNECT_INTERVAL_SECONDS", 0.01)
        monkeypatch.setattr(tracking, "MAX_RECONNECT_ATTEMPTS", 1)
        monkeypatch.setattr(tracking, "_open_capture", lambda url: None)

        assert session._reconnect_loop() is None

        assert recorder.types() == ["tracking_reconnecting"]

    def test_a_camera_that_cannot_be_opened_records_an_error_and_never_a_start(self):
        recorder = FakeRecorder()
        session = TrackingSession(
            uuid.uuid4(), "rtsp://127.0.0.1:1/does-not-exist", None, None, None, None, ["qr"], recorder
        )

        session.start()
        session._thread.join(timeout=30)

        assert recorder.types() == ["tracking_error"]
        assert "Could not open stream" in recorder.events[0].value


class TestHeatHandOff:
    def _session(self, recorder, now, monotonic):
        session = _session(recorder)
        session._heatmap = HeatmapAccumulator(800, 400)
        session._now = lambda: now["t"]
        session._monotonic = lambda: monotonic["t"]
        return session

    def _setup(self, start=datetime(2026, 3, 10, 10, 20, tzinfo=timezone.utc)):
        recorder = FakeRecorder()
        now, monotonic = {"t": start}, {"t": 1000.0}
        session = self._session(recorder, now, monotonic)
        session._flush_heat()  # first call: initialises the period/interval, nothing to hand off
        return session, recorder, now, monotonic

    def test_nothing_is_handed_off_before_the_interval_or_an_hour_change(self):
        session, recorder, now, monotonic = self._setup()
        session._heatmap.add([Point(100, 100)] * 5)

        monotonic["t"] += HEAT_FLUSH_INTERVAL_SECONDS - 1
        session._flush_heat()

        assert recorder.heat == []

    def test_the_interval_hands_off_the_delta_attributed_to_the_current_hour(self):
        session, recorder, now, monotonic = self._setup()
        session._heatmap.add([Point(100, 100)] * 5 + [Point(700, 300)] * 2)

        monotonic["t"] += HEAT_FLUSH_INTERVAL_SECONDS + 1
        session._flush_heat()

        (delta,) = recorder.heat
        assert delta.camera_id == session.camera_id
        assert delta.period_start == datetime(2026, 3, 10, 10, 0, tzinfo=timezone.utc)
        assert (delta.frame_width, delta.frame_height) == (800, 400)
        assert delta.samples == 7
        assert delta.grid.sum() == 7 and delta.grid[10, 10] == 5 and delta.grid[30, 70] == 2

    def test_each_hand_off_carries_only_what_is_new(self):
        session, recorder, now, monotonic = self._setup()
        session._heatmap.add([Point(100, 100)] * 5)
        monotonic["t"] += HEAT_FLUSH_INTERVAL_SECONDS + 1
        session._flush_heat()

        session._heatmap.add([Point(100, 100)] * 3)
        monotonic["t"] += HEAT_FLUSH_INTERVAL_SECONDS + 1
        session._flush_heat()

        assert [d.samples for d in recorder.heat] == [5, 3]

    def test_nothing_new_means_nothing_handed_off(self):
        session, recorder, now, monotonic = self._setup()

        monotonic["t"] += HEAT_FLUSH_INTERVAL_SECONDS + 1
        session._flush_heat()

        assert recorder.heat == []

    def test_an_hour_change_hands_off_early_attributed_to_the_hour_just_ended(self):
        session, recorder, now, monotonic = self._setup(datetime(2026, 3, 10, 10, 58, tzinfo=timezone.utc))
        session._heatmap.add([Point(100, 100)] * 4)

        now["t"] = datetime(2026, 3, 10, 11, 0, 3, tzinfo=timezone.utc)  # only seconds of wall clock later
        session._flush_heat()

        (delta,) = recorder.heat
        assert delta.period_start == datetime(2026, 3, 10, 10, 0, tzinfo=timezone.utc)  # the hour it was collected in
        assert session._heat_period == datetime(2026, 3, 10, 11, 0, tzinfo=timezone.utc)

        session._heatmap.add([Point(100, 100)] * 2)
        monotonic["t"] += HEAT_FLUSH_INTERVAL_SECONDS + 1
        session._flush_heat()
        assert recorder.heat[1].period_start == datetime(2026, 3, 10, 11, 0, tzinfo=timezone.utc)

    def test_stopping_forces_the_final_hand_off(self):
        session, recorder, now, monotonic = self._setup()
        session._heatmap.add([Point(100, 100)] * 3)

        session._flush_heat(force=True)  # what _run's finally does

        assert [d.samples for d in recorder.heat] == [3]

    def test_the_live_heatmap_is_undisturbed_by_handing_off(self):
        session, recorder, now, monotonic = self._setup()
        session._heatmap.add([Point(100, 100)] * 3)

        session._flush_heat(force=True)

        assert session._heatmap.sample_count == 3  # the live view still has it all
        frame = np.full((400, 800, 3), 128, np.uint8)
        assert (session._heatmap.render(frame) != frame).any()

    def test_without_a_recorder_or_a_heatmap_it_is_a_no_op(self):
        no_recorder = _session(None)
        no_recorder._heatmap = HeatmapAccumulator(800, 400)
        no_recorder._heatmap.add([Point(1, 1)])
        no_recorder._flush_heat(force=True)  # nothing to assert but that it doesn't raise
        assert no_recorder._heatmap.sample_count == 1

        no_heatmap = _session(FakeRecorder())
        no_heatmap._flush_heat(force=True)


# -- real end to end ---------------------------------------------------------------------


def _create_camera(client, video_path, modules) -> str:
    response = client.post("/cameras", json={"name": "Street", "rtsp_url": video_path, "enabled_modules": modules})
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _wait_for(client, camera_id, done, timeout=90):
    deadline = time.monotonic() + timeout
    status = None
    while time.monotonic() < deadline:
        status = client.get(f"/cameras/{camera_id}/tracking/status").json()
        if status["status"] == "error":
            pytest.fail(f"tracking errored: {status}")
        if done(status):
            return status
        time.sleep(0.2)
    pytest.fail(f"condition not met within {timeout}s; last status: {status}")


def _all_events(client, camera_id) -> list[dict]:
    return client.get("/events", params={"camera_id": camera_id, "limit": 500}).json()["events"]


def test_real_tracking_persists_crossings_zone_events_uptime_and_heat(client, panning_video):
    video_path, width, _height = panning_video
    camera_id = _create_camera(client, video_path, ["people", "vehicles"])
    # The same line as the Phase 8 vehicle test: the bus and two people cross x=450.
    fraction = 450 / width
    client.post(f"/cameras/{camera_id}/lines", json={"name": "Kerb", "x1": fraction, "y1": 0.0, "x2": fraction, "y2": 1.0})
    whole = [{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0}, {"x": 1.0, "y": 1.0}, {"x": 0.0, "y": 1.0}]
    client.post(f"/cameras/{camera_id}/zones", json={"name": "Whole frame", "points": whole})

    assert client.post(f"/cameras/{camera_id}/tracking/start").status_code == 200
    try:
        status = _wait_for(
            client,
            camera_id,
            lambda s: s["line_counts"]
            and s["line_counts"][0]["in_count"] + s["line_counts"][0]["out_count"] > 0
            and s["line_counts"][0]["vehicle_in_count"] + s["line_counts"][0]["vehicle_out_count"] > 0,
        )
    finally:
        client.post(f"/cameras/{camera_id}/tracking/stop")
    assert event_recorder.flush(timeout=30)

    events = _all_events(client, camera_id)
    by_type: dict[str, list[dict]] = {}
    for event in events:
        by_type.setdefault(event["event_type"], []).append(event)

    # Uptime: it started, and stopping (via the API) recorded the stop.
    assert len(by_type["tracking_started"]) == 1
    assert len(by_type["tracking_stopped"]) >= 1
    assert "tracking_error" not in by_type

    # Real crossings, for both people and vehicles, attributed to the line by name.
    crossings = by_type["line_crossed"]
    assert {e["category"] for e in crossings} == {"person", "vehicle"}
    assert {e["subject_name"] for e in crossings} == {"Kerb"}
    assert {e["direction"] for e in crossings} <= {"in", "out"}
    # The events agree with what the live counters said at the moment we looked (the
    # session may have counted a little more between that status and stopping).
    counted_people = status["line_counts"][0]["in_count"] + status["line_counts"][0]["out_count"]
    counted_vehicles = status["line_counts"][0]["vehicle_in_count"] + status["line_counts"][0]["vehicle_out_count"]
    assert len([e for e in crossings if e["category"] == "person"]) >= counted_people
    assert len([e for e in crossings if e["category"] == "vehicle"]) >= counted_vehicles

    # Zone: people were tracked inside the whole-frame zone.
    assert any(e["subject_name"] == "Whole frame" and e["category"] == "person" for e in by_type["zone_entered"])

    # Newest first, and started before anything else happened.
    times = [e["occurred_at"] for e in events]
    assert times == sorted(times, reverse=True)
    assert events[-1]["event_type"] == "tracking_started"

    # The heat was saved when tracking stopped.
    info = client.get("/analytics/heatmap/info", params={"camera_id": camera_id, "since": "2000-01-01T00:00:00Z"}).json()
    assert info["available"] and info["samples"] > 0

    # And the analytics totals are exactly what the events say.
    summary = client.get("/analytics/summary", params={"camera_id": camera_id, "since": "2000-01-01T00:00:00Z"}).json()
    assert summary["people_in"] + summary["people_out"] == len([e for e in crossings if e["category"] == "person"])
    assert summary["vehicle_in"] + summary["vehicle_out"] == len([e for e in crossings if e["category"] == "vehicle"])
    assert summary["lines"][0]["name"] == "Kerb"
    assert summary["zones"][0]["entered"] == len(by_type["zone_entered"])


def test_a_real_code_in_view_produces_one_read_event_not_one_per_frame(client, scan_video):
    camera_id = _create_camera(client, scan_video.path, ["qr", "barcode"])
    assert client.post(f"/cameras/{camera_id}/tracking/start").status_code == 200
    try:
        _wait_for(client, camera_id, lambda s: {r["kind"] for r in s["reads"]} >= {"qr", "barcode"}, timeout=60)
        # Let plenty more frames go by with the codes still in view.
        time.sleep(1.5)
    finally:
        client.post(f"/cameras/{camera_id}/tracking/stop")
    assert event_recorder.flush(timeout=30)

    reads = [e for e in _all_events(client, camera_id) if e["event_type"] == "read"]
    assert sorted((e["category"], e["value"]) for e in reads) == [
        ("barcode", scan_video.barcode),
        ("qr", scan_video.qr),
    ]
    assert {e["detail"] for e in reads} == {"QR Code", "Code 128"}


def test_an_unreachable_camera_records_only_an_error_event(client):
    camera_id = _create_camera(client, "rtsp://127.0.0.1:1/does-not-exist", ["people"])

    client.post(f"/cameras/{camera_id}/tracking/start")
    _wait_for_error = time.monotonic() + 30
    while time.monotonic() < _wait_for_error:
        if client.get(f"/cameras/{camera_id}/tracking/status").json()["status"] == "error":
            break
        time.sleep(0.2)
    client.post(f"/cameras/{camera_id}/tracking/stop")
    assert event_recorder.flush(timeout=30)

    events = _all_events(client, camera_id)
    assert [e["event_type"] for e in events] == ["tracking_error"]
    assert "Could not open stream" in events[0]["value"]
