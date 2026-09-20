"""Zone occupancy and the heatmap inside TrackingSession: direct tests of the per-frame
update methods with synthetic sequential positions (no video/model — same style as
test_tracking_counting.py), the drawn overlay, and one real end-to-end test proving actual
YOLO detection + ByteTrack tracking + zone counting + heat accumulation work together.
"""
import time
import uuid
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from app.counting import Point
from app.heatmap import HeatmapAccumulator
from app.tracking import TrackingSession, _draw_and_encode, tracking_manager
from app.zones import ZoneConfig


def _zone_config(points, name="Test zone") -> ZoneConfig:
    return ZoneConfig(id=uuid.uuid4(), name=name, points=tuple(Point(x, y) for x, y in points))


# The left half of the frame, as normalized coordinates.
LEFT_HALF = [(0.0, 0.0), (0.5, 0.0), (0.5, 1.0), (0.0, 1.0)]
RIGHT_HALF = [(0.5, 0.0), (1.0, 0.0), (1.0, 1.0), (0.5, 1.0)]


def _session_with_zones(*zone_configs: ZoneConfig, width=1000, height=1000) -> TrackingSession:
    session = TrackingSession(uuid.uuid4(), "unused://", None, None, None, list(zone_configs))
    session._resolved_zones = [zc.to_pixels(width, height) for zc in zone_configs]
    return session


def _counts_by_name(session: TrackingSession) -> dict:
    return {zc["name"]: zc["count"] for zc in session.snapshot().zone_counts}


class TestUpdateZonesDirectly:
    def test_a_track_inside_a_zone_is_counted(self):
        session = _session_with_zones(_zone_config(LEFT_HALF, "Left"))

        session._update_zones({1: Point(200, 500)})

        assert _counts_by_name(session) == {"Left": 1}

    def test_a_track_outside_a_zone_is_not_counted(self):
        session = _session_with_zones(_zone_config(LEFT_HALF, "Left"))

        session._update_zones({1: Point(800, 500)})

        assert _counts_by_name(session) == {"Left": 0}

    def test_the_count_is_live_so_it_drops_when_a_track_leaves(self):
        session = _session_with_zones(_zone_config(LEFT_HALF, "Left"))

        session._update_zones({1: Point(200, 500), 2: Point(300, 500)})
        assert _counts_by_name(session) == {"Left": 2}

        session._update_zones({1: Point(800, 500), 2: Point(300, 500)})  # track 1 walks out
        assert _counts_by_name(session) == {"Left": 1}

        session._update_zones({})  # nobody visible
        assert _counts_by_name(session) == {"Left": 0}

    def test_each_zone_counts_independently(self):
        session = _session_with_zones(_zone_config(LEFT_HALF, "Left"), _zone_config(RIGHT_HALF, "Right"))

        session._update_zones({1: Point(100, 500), 2: Point(200, 500), 3: Point(900, 500)})

        assert _counts_by_name(session) == {"Left": 2, "Right": 1}

    def test_overlapping_zones_both_count_the_same_track(self):
        whole = _zone_config([(0, 0), (1, 0), (1, 1), (0, 1)], "Whole")
        session = _session_with_zones(whole, _zone_config(LEFT_HALF, "Left"))

        session._update_zones({1: Point(200, 500)})

        assert _counts_by_name(session) == {"Whole": 1, "Left": 1}

    def test_a_non_rectangular_zone_uses_its_real_shape(self):
        triangle = _zone_config([(0.0, 0.0), (1.0, 0.0), (0.5, 1.0)], "Triangle")
        session = _session_with_zones(triangle)

        session._update_zones({1: Point(500, 300), 2: Point(50, 900)})  # inside; bounding box only

        assert _counts_by_name(session) == {"Triangle": 1}

    def test_zones_are_listed_with_zero_before_any_frame_has_been_processed(self):
        # A session still warming up hasn't resolved its zones to pixels yet.
        session = TrackingSession(uuid.uuid4(), "unused://", None, None, None, [_zone_config(LEFT_HALF, "Left")])

        assert session._resolved_zones is None
        session._update_zones({1: Point(200, 500)})  # must not crash before resolution
        assert _counts_by_name(session) == {"Left": 0}

    def test_a_session_with_no_zones_reports_none(self):
        session = TrackingSession(uuid.uuid4(), "unused://", None, None)

        session._update_zones({1: Point(200, 500)})

        assert session.snapshot().zone_counts == []

    def test_the_snapshot_carries_each_zones_id_and_name(self):
        config = _zone_config(LEFT_HALF, "Checkout")
        session = _session_with_zones(config)

        session._update_zones({1: Point(100, 100)})

        assert session.snapshot().zone_counts == [{"zone_id": str(config.id), "name": "Checkout", "count": 1}]


class TestDrawingZones:
    def _draw(self, resolved_zones, zone_counts):
        frame = np.zeros((200, 200, 3), dtype=np.uint8)
        jpeg, track_ids = _draw_and_encode(frame, SimpleNamespace(boxes=[]), [], {}, resolved_zones, zone_counts)
        assert track_ids == []
        return cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)

    def test_a_zone_is_filled_and_labelled_on_the_frame(self):
        config = _zone_config([(0.25, 0.25), (0.75, 0.25), (0.75, 0.75), (0.25, 0.75)], "Checkout")
        decoded = self._draw([config.to_pixels(200, 200)], {config.id: 2})

        assert decoded[100, 100, 1] > 20  # translucent fill inside the zone (green channel)
        assert decoded[5, 5].max() < 10  # untouched outside it
        assert decoded[28:46, 50:200, 2].max() > 150  # the "Checkout: 2 inside" label above the zone

    def test_no_zones_leaves_the_frame_untouched(self):
        decoded = self._draw([], {})

        assert decoded.max() < 10


class TestHeatmapInLatestFrame:
    def _session_with_a_recorded_frame(self):
        session = TrackingSession(uuid.uuid4(), "unused://", None, None)
        frame = np.full((400, 800, 3), 128, dtype=np.uint8)
        ok, encoded = cv2.imencode(".jpg", frame)
        assert ok
        session._record_frame(encoded.tobytes(), [], frame)
        return session

    def test_without_heatmap_the_stored_jpeg_is_returned_unchanged(self):
        session = self._session_with_a_recorded_frame()

        assert session.latest_frame() == session._latest_jpeg
        assert session.latest_frame(heatmap=False) == session._latest_jpeg

    def test_asking_for_the_heatmap_before_one_exists_falls_back_to_the_plain_frame(self):
        session = self._session_with_a_recorded_frame()

        assert session._heatmap is None
        assert session.latest_frame(heatmap=True) == session._latest_jpeg

    def test_asking_for_the_heatmap_before_any_heat_is_collected_falls_back_to_the_plain_frame(self):
        session = self._session_with_a_recorded_frame()
        session._heatmap = HeatmapAccumulator(800, 400)

        assert session.latest_frame(heatmap=True) == session._latest_jpeg

    def test_with_heat_collected_the_returned_frame_is_tinted_where_people_stood(self):
        session = self._session_with_a_recorded_frame()
        session._heatmap = HeatmapAccumulator(800, 400)
        session._heatmap.add([Point(400, 200)] * 30)

        heat_jpeg = session.latest_frame(heatmap=True)

        assert heat_jpeg != session._latest_jpeg
        decoded = cv2.imdecode(np.frombuffer(heat_jpeg, np.uint8), cv2.IMREAD_COLOR)
        assert decoded.shape == (400, 800, 3)
        assert np.abs(decoded[200, 400].astype(int) - 128).max() > 40  # the hot spot
        assert np.abs(decoded[5, 5].astype(int) - 128).max() < 6  # far away: still the original grey

    def test_the_plain_frame_is_still_available_after_a_heatmap_request(self):
        session = self._session_with_a_recorded_frame()
        session._heatmap = HeatmapAccumulator(800, 400)
        session._heatmap.add([Point(400, 200)] * 30)
        plain_before = session.latest_frame()

        session.latest_frame(heatmap=True)

        assert session.latest_frame() == plain_before


def _create_camera(client, **overrides) -> dict:
    body = {"name": "Panning camera", "rtsp_url": "rtsp://127.0.0.1:1/unused"}
    body.update(overrides)
    return client.post("/cameras", json=body).json()


def test_latest_frame_with_heatmap_404s_before_tracking_has_ever_started(client):
    camera_id = _create_camera(client)["id"]

    response = client.get(f"/cameras/{camera_id}/tracking/latest-frame?heatmap=true")

    assert response.status_code == 404


def test_a_stopped_or_unstarted_cameras_status_lists_no_zone_counts(client):
    camera_id = _create_camera(client)["id"]

    assert client.get(f"/cameras/{camera_id}/tracking/status").json()["zone_counts"] == []


def test_real_tracked_people_are_counted_in_a_zone_and_leave_heat_on_the_frame(client, panning_video):
    video_path, _width, _height = panning_video
    camera_id = _create_camera(client, rtsp_url=video_path)["id"]
    whole_frame = [{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0}, {"x": 1.0, "y": 1.0}, {"x": 0.0, "y": 1.0}]
    corner = [{"x": 0.0, "y": 0.0}, {"x": 0.02, "y": 0.0}, {"x": 0.02, "y": 0.02}]  # nobody's feet are up here
    client.post(f"/cameras/{camera_id}/zones", json={"name": "Whole frame", "points": whole_frame})
    client.post(f"/cameras/{camera_id}/zones", json={"name": "Corner", "points": corner})

    assert client.post(f"/cameras/{camera_id}/tracking/start").status_code == 200

    try:
        deadline = time.monotonic() + 45
        counts = {}
        while time.monotonic() < deadline:
            status = client.get(f"/cameras/{camera_id}/tracking/status").json()
            if status["status"] == "error":
                pytest.fail(f"tracking errored: {status}")
            counts = {z["name"]: z["count"] for z in status["zone_counts"]}
            if counts.get("Whole frame", 0) >= 1:
                break
            time.sleep(0.1)
        else:
            pytest.fail(f"no tracked person was ever counted inside the whole-frame zone; last counts: {counts}")

        assert counts["Corner"] == 0

        # Freeze the session on its final frame (stop() is the public API; the session
        # stays registered, so latest-frame still serves it). Otherwise the plain and
        # heatmap requests below would be different video frames and any difference
        # between them wouldn't prove the heat overlay is what changed.
        tracking_manager.get(uuid.UUID(camera_id)).stop()

        plain_response = client.get(f"/cameras/{camera_id}/tracking/latest-frame")
        heat_response = client.get(f"/cameras/{camera_id}/tracking/latest-frame?heatmap=true")
    finally:
        client.post(f"/cameras/{camera_id}/tracking/stop")

    assert plain_response.status_code == 200
    assert heat_response.status_code == 200
    assert plain_response.headers["content-type"] == "image/jpeg"
    assert heat_response.headers["content-type"] == "image/jpeg"

    plain = cv2.imdecode(np.frombuffer(plain_response.content, np.uint8), cv2.IMREAD_COLOR)
    heat = cv2.imdecode(np.frombuffer(heat_response.content, np.uint8), cv2.IMREAD_COLOR)
    assert plain.shape == heat.shape
    difference = np.abs(plain.astype(int) - heat.astype(int))
    assert difference.max() > 40, "the heatmap request returned a frame with no visible heat overlay"
    assert difference[:40, :40].mean() < 2, "heat should only tint where people actually stood"
