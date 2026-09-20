"""Line-crossing counting: a direct test of TrackingSession's count-update method with
synthetic sequential positions (no video/model — same style as test_tracking.py's
direct `_reconnect_loop()` test), plus one real end-to-end test proving actual YOLO
detection + ByteTrack tracking + crossing counting work together.

For the end-to-end case, a video of a *static* repeated image (as used elsewhere for
connection/detection tests) has no movement, so it can't exercise crossing detection.
The shared `panning_video` fixture (tests/conftest.py) pans a cropped window across the
real bus.jpg photo instead, which gives tracked people genuine, monotonic motion.
"""
import time
import uuid

import pytest

from app.counting import LineConfig, Point
from app.tracking import TrackingSession


def _line_config(x1=0.5, y1=1.0, x2=0.5, y2=0.0, **overrides) -> LineConfig:
    # Bottom-to-top by default so that, under classify_crossing's convention (see
    # test_counting.py), moving left-to-right registers as "in" — makes the tests
    # below read naturally. Direction is a function of point order, not special-cased.
    return LineConfig(id=uuid.uuid4(), name="Test line", x1=x1, y1=y1, x2=x2, y2=y2, **overrides)


def _session_with_resolved_line(line_config: LineConfig, width=1000, height=1000) -> TrackingSession:
    session = TrackingSession(uuid.uuid4(), "unused://", None, None, [line_config])
    session._resolved_lines = [line_config.to_pixels(width, height)]
    return session


class TestUpdateCountsDirectly:
    def test_a_track_crossing_left_to_right_increments_in(self):
        line_config = _line_config(x1=0.5, y1=1.0, x2=0.5, y2=0.0)  # vertical line at x=500 of a 1000-wide frame
        session = _session_with_resolved_line(line_config)

        session._update_counts({1: Point(400, 500)})  # left of the line
        session._update_counts({1: Point(600, 500)})  # now right of the line -> crossed

        counts = session.snapshot().line_counts
        assert counts == [{"line_id": str(line_config.id), "name": "Test line", "in_count": 1, "out_count": 0}]

    def test_the_same_track_crossing_back_increments_out(self):
        line_config = _line_config()
        session = _session_with_resolved_line(line_config)

        session._update_counts({1: Point(400, 500)})
        session._update_counts({1: Point(600, 500)})  # in
        session._update_counts({1: Point(400, 500)})  # back across -> out

        counts = {c["line_id"]: c for c in session.snapshot().line_counts}[str(line_config.id)]
        assert counts["in_count"] == 1
        assert counts["out_count"] == 1

    def test_no_crossing_when_a_track_stays_on_one_side(self):
        line_config = _line_config()
        session = _session_with_resolved_line(line_config)

        session._update_counts({1: Point(100, 500)})
        session._update_counts({1: Point(150, 500)})
        session._update_counts({1: Point(200, 500)})

        counts = session.snapshot().line_counts[0]
        assert counts["in_count"] == 0
        assert counts["out_count"] == 0

    def test_a_brand_new_track_id_with_no_prior_position_does_not_count(self):
        line_config = _line_config()
        session = _session_with_resolved_line(line_config)

        session._update_counts({1: Point(600, 500)})  # first sighting, right of the line, no "previous" to compare

        counts = session.snapshot().line_counts[0]
        assert counts["in_count"] == 0
        assert counts["out_count"] == 0

    def test_multiple_tracks_and_multiple_lines_are_counted_independently(self):
        line_a = _line_config(x1=0.3, y1=1.0, x2=0.3, y2=0.0)
        line_b = _line_config(x1=0.7, y1=1.0, x2=0.7, y2=0.0)
        session = TrackingSession(uuid.uuid4(), "unused://", None, None, [line_a, line_b])
        session._resolved_lines = [line_a.to_pixels(1000, 1000), line_b.to_pixels(1000, 1000)]

        session._update_counts({1: Point(250, 500), 2: Point(650, 500)})
        session._update_counts({1: Point(350, 500), 2: Point(750, 500)})  # track 1 crosses line_a, track 2 crosses line_b

        by_id = {c["line_id"]: c for c in session.snapshot().line_counts}
        assert by_id[str(line_a.id)] == {"line_id": str(line_a.id), "name": "Test line", "in_count": 1, "out_count": 0}
        assert by_id[str(line_b.id)] == {"line_id": str(line_b.id), "name": "Test line", "in_count": 1, "out_count": 0}

    def test_a_track_that_disappears_and_a_new_one_reusing_the_id_does_not_falsely_cross(self):
        # _previous_positions is fully replaced each call, so a track missing from one
        # frame has no stale "previous" position to wrongly compare against later.
        line_config = _line_config()
        session = _session_with_resolved_line(line_config)

        session._update_counts({1: Point(400, 500)})
        session._update_counts({})  # track 1 disappears for a frame
        session._update_counts({1: Point(600, 500)})  # "reappears" on the other side

        counts = session.snapshot().line_counts[0]
        assert counts["in_count"] == 0
        assert counts["out_count"] == 0


def _create_camera(client, **overrides) -> dict:
    body = {"name": "Panning camera", "rtsp_url": "rtsp://127.0.0.1:1/unused"}
    body.update(overrides)
    return client.post("/cameras", json=body).json()


def test_a_real_tracked_person_crossing_a_real_line_increments_a_real_count(client, panning_video):
    video_path, width, _height = panning_video
    # Verified by hand (see the module docstring): one tracked person's box moves from
    # x~583 down to x~43 across this exact video, crossing x=300 around frame 13-14.
    # Placed at half the video's width so this holds regardless of exact pixel size.
    line_x_fraction = 300 / width
    camera_id = _create_camera(client, rtsp_url=video_path)["id"]
    client.post(
        f"/cameras/{camera_id}/lines",
        json={"name": "Midline", "x1": line_x_fraction, "y1": 0.0, "x2": line_x_fraction, "y2": 1.0},
    )

    assert client.post(f"/cameras/{camera_id}/tracking/start").status_code == 200

    deadline = time.monotonic() + 30
    status = None
    try:
        while time.monotonic() < deadline:
            status = client.get(f"/cameras/{camera_id}/tracking/status").json()
            if status["status"] == "error":
                pytest.fail(f"tracking errored: {status}")
            counts = status["line_counts"][0] if status["line_counts"] else None
            if counts and (counts["in_count"] + counts["out_count"]) > 0:
                break
            time.sleep(0.2)
        else:
            pytest.fail(f"no crossing detected within 30s; last status: {status}")
    finally:
        client.post(f"/cameras/{camera_id}/tracking/stop")

    counts = status["line_counts"][0]
    assert counts["name"] == "Midline"
    assert counts["in_count"] + counts["out_count"] >= 1
