"""Vehicle detection/counting inside TrackingSession: direct tests of the count and drawing
logic with stub detections (no video/model — same style as test_tracking_counting.py), and
real end-to-end tests proving actual YOLO detection + ByteTrack tracking of the bus in the
panning test video counts as a *vehicle* crossing a line, separately from the people.
"""
import time
import uuid
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from app.counting import LineConfig, Point
from app.tracking import TrackingSession, _draw_and_encode, _line_label, _track_points


def _line_config(x1=0.5, y1=1.0, x2=0.5, y2=0.0) -> LineConfig:
    # Bottom-to-top, so left-to-right movement registers as "in" (see test_counting.py).
    return LineConfig(id=uuid.uuid4(), name="Gate", x1=x1, y1=y1, x2=x2, y2=y2)


def _session(line_config, modules=None) -> TrackingSession:
    session = TrackingSession(uuid.uuid4(), "unused://", None, None, [line_config], None, modules)
    session._resolved_lines = [line_config.to_pixels(1000, 1000)]
    return session


def _counts(session: TrackingSession) -> dict:
    (entry,) = session.snapshot().line_counts
    return {k: entry[k] for k in ("in_count", "out_count", "vehicle_in_count", "vehicle_out_count")}


class TestSessionModules:
    def test_a_session_created_the_old_way_is_people_only(self):
        session = TrackingSession(uuid.uuid4(), "unused://", None, None)

        assert session._modules == frozenset({"people"})
        assert session._class_ids == [0]

    def test_the_modules_decide_which_classes_are_detected(self):
        def class_ids(modules):
            return TrackingSession(uuid.uuid4(), "unused://", None, None, None, None, modules)._class_ids

        assert class_ids(["vehicles"]) == [2, 3, 5, 7]
        assert class_ids(["people", "vehicles"]) == [0, 2, 3, 5, 7]
        assert class_ids(["qr", "barcode", "ocr"]) == []  # no detector at all

    def test_only_the_enabled_reading_modules_get_a_scanner_or_worker(self):
        people = TrackingSession(uuid.uuid4(), "unused://", None, None)
        assert people._code_scanner is None and people._ocr_worker is None

        qr = TrackingSession(uuid.uuid4(), "unused://", None, None, None, None, ["qr"])
        assert qr._code_scanner is not None and qr._ocr_worker is None

        ocr = TrackingSession(uuid.uuid4(), "unused://", None, None, None, None, ["ocr"])
        assert ocr._code_scanner is None and ocr._ocr_worker is not None


class TestVehicleCountsDirectly:
    def test_a_vehicle_crossing_counts_as_a_vehicle_not_a_person(self):
        session = _session(_line_config())

        session._update_counts({7: Point(400, 500)}, "vehicle")
        session._update_counts({7: Point(600, 500)}, "vehicle")  # left to right: in

        assert _counts(session) == {"in_count": 0, "out_count": 0, "vehicle_in_count": 1, "vehicle_out_count": 0}

    def test_a_vehicle_crossing_back_counts_as_vehicle_out(self):
        session = _session(_line_config())

        for x in (400, 600, 400):
            session._update_counts({7: Point(x, 500)}, "vehicle")

        assert _counts(session) == {"in_count": 0, "out_count": 0, "vehicle_in_count": 1, "vehicle_out_count": 1}

    def test_people_and_vehicles_are_counted_independently_even_with_the_same_track_id(self):
        session = _session(_line_config())

        session._update_counts({1: Point(400, 500)}, "person")
        session._update_counts({1: Point(300, 500)}, "vehicle")
        session._update_counts({1: Point(600, 500)}, "person")  # the person crosses in
        session._update_counts({1: Point(200, 500)}, "vehicle")  # the vehicle stays on its side

        assert _counts(session) == {"in_count": 1, "out_count": 0, "vehicle_in_count": 0, "vehicle_out_count": 0}

    def test_the_default_group_is_person(self):
        session = _session(_line_config())

        session._update_counts({1: Point(400, 500)})
        session._update_counts({1: Point(600, 500)})

        assert _counts(session)["in_count"] == 1

    def test_a_track_that_flips_between_person_and_vehicle_does_not_cross_falsely(self):
        # A person briefly detected as a bus (seen in the real footage) must not be
        # compared against the position it had in the other group.
        session = _session(_line_config())

        session._update_counts({4: Point(400, 500)}, "person")
        session._update_counts({4: Point(600, 500)}, "vehicle")  # same id, other group, other side

        assert _counts(session) == {"in_count": 0, "out_count": 0, "vehicle_in_count": 0, "vehicle_out_count": 0}

    def test_vehicles_seen_for_the_first_time_are_not_counted(self):
        session = _session(_line_config())

        session._update_counts({9: Point(900, 500)}, "vehicle")

        assert _counts(session)["vehicle_in_count"] == 0

    def test_the_status_lists_active_vehicle_track_ids_separately_from_people(self):
        session = _session(_line_config())

        session._record_frame(b"jpeg", [1, 2], np.zeros((10, 10, 3), np.uint8), [5, 6, 7])

        snapshot = session.snapshot()
        assert snapshot.active_track_ids == [1, 2]
        assert snapshot.active_vehicle_track_ids == [5, 6, 7]


class _Scalar:
    def __init__(self, value):
        self._value = value

    def item(self):
        return self._value


class _Row:
    def __init__(self, values):
        self._values = values

    def tolist(self):
        return list(self._values)


def _box(class_id, track_id, xyxy):
    return SimpleNamespace(
        cls=_Scalar(class_id),
        id=None if track_id is None else _Scalar(track_id),
        xyxy=[_Row(xyxy)],
    )


NAMES = {0: "person", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}


class TestTrackPoints:
    def _result(self):
        return SimpleNamespace(
            names=NAMES,
            boxes=[
                _box(0, 1, (100, 100, 200, 300)),  # person
                _box(5, 2, (300, 100, 500, 260)),  # bus
                _box(2, 3, (600, 200, 700, 260)),  # car
                _box(0, None, (10, 10, 20, 30)),  # person the tracker hasn't identified yet
            ],
        )

    def test_people_are_the_default_and_use_the_feet_position(self):
        assert _track_points(self._result()) == {1: Point(150, 300)}

    def test_vehicle_classes_are_selected_by_class_id(self):
        from app.modules import VEHICLE_CLASS_IDS

        assert _track_points(self._result(), VEHICLE_CLASS_IDS) == {2: Point(400, 260), 3: Point(650, 260)}

    def test_boxes_without_a_track_id_are_skipped(self):
        assert len(_track_points(self._result(), (0, 2, 3, 5, 7))) == 3


class TestLineLabel:
    COUNTS = {"in": 3, "out": 1, "vehicle_in": 2, "vehicle_out": 5}

    def test_people_only_reads_exactly_as_before_vehicles_existed(self):
        assert _line_label("Gate", self.COUNTS, ["people"]) == "Gate: 3 in / 1 out"

    def test_vehicles_only_shows_just_the_vehicle_counts(self):
        assert _line_label("Gate", self.COUNTS, ["vehicles"]) == "Gate: veh 2 in / 5 out"

    def test_both_show_people_then_vehicles(self):
        assert _line_label("Gate", self.COUNTS, ["people", "vehicles"]) == "Gate: 3 in / 1 out | veh 2 in / 5 out"

    def test_neither_shows_just_the_name(self):
        assert _line_label("Gate", self.COUNTS, ["qr"]) == "Gate"


class TestDrawingVehicles:
    def _draw(self, result, modules):
        frame = np.zeros((300, 400, 3), np.uint8)
        jpeg = _draw_and_encode(frame, result, [], {}, [], {}, modules=modules)
        return cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)

    def _edge_colour(self, decoded, x1, y1):
        return decoded[y1 - 1 : y1 + 2, x1 + 20 : x1 + 60].reshape(-1, 3).max(axis=0).astype(int)

    def test_people_and_vehicles_are_boxed_in_different_colours(self):
        result = SimpleNamespace(
            names=NAMES,
            boxes=[_box(0, 1, (20, 100, 120, 250)), _box(5, 2, (200, 100, 340, 250))],
        )

        decoded = self._draw(result, ["people", "vehicles"])

        person, vehicle = self._edge_colour(decoded, 20, 100), self._edge_colour(decoded, 200, 100)
        assert person[1] > 150 and person[2] < 80  # green: BOX_COLOR (0, 200, 0)
        assert vehicle[2] > 200 and vehicle[0] < 80  # orange: VEHICLE_COLOR (0, 140, 255)

    def test_a_detector_less_camera_draws_no_boxes_and_does_not_crash(self):
        decoded = self._draw(None, ["qr"])

        assert decoded.max() < 10


@pytest.mark.parametrize("modules", [["vehicles"], ["people", "vehicles"]])
def test_a_real_tracked_bus_is_counted_as_a_vehicle_crossing_a_line(client, panning_video, modules):
    video_path, width, _height = panning_video
    # The real detector tracks the bus (a vehicle) across this whole panning video, its
    # feet moving from x~567 to x~277 (verified by hand while planning this phase), so a
    # line at x=450 is crossed once. Two of the people cross that same line as well,
    # which is exactly what lets the "people" case prove the two counts stay separate.
    camera = client.post(
        "/cameras", json={"name": "Street", "rtsp_url": video_path, "enabled_modules": modules}
    ).json()
    camera_id = camera["id"]
    fraction = 450 / width
    client.post(f"/cameras/{camera_id}/lines", json={"name": "Kerb", "x1": fraction, "y1": 0.0, "x2": fraction, "y2": 1.0})

    assert client.post(f"/cameras/{camera_id}/tracking/start").status_code == 200

    expects_people = "people" in modules
    deadline = time.monotonic() + 60
    status, counts = None, None
    try:
        while time.monotonic() < deadline:
            status = client.get(f"/cameras/{camera_id}/tracking/status").json()
            if status["status"] == "error":
                pytest.fail(f"tracking errored: {status}")
            counts = status["line_counts"][0] if status["line_counts"] else None
            if counts and counts["vehicle_in_count"] + counts["vehicle_out_count"] > 0:
                if not expects_people or counts["in_count"] + counts["out_count"] > 0:
                    break
            time.sleep(0.2)
        else:
            pytest.fail(f"expected crossings not seen within 60s; last status: {status}")
    finally:
        client.post(f"/cameras/{camera_id}/tracking/stop")

    assert counts["vehicle_in_count"] + counts["vehicle_out_count"] >= 1
    if expects_people:
        assert counts["in_count"] + counts["out_count"] >= 1
    else:
        # Vehicles-only: people were never even detected, so nothing lands in the people counts.
        assert counts["in_count"] == counts["out_count"] == 0
        assert status["active_track_ids"] == []
