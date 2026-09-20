"""Detection+tracking session tests. Real OpenCV, real YOLO/ByteTrack, real PostgreSQL,
no mocks — same standard as test_detection_pipeline.py / test_camera_connection.py.

As in test_camera_connection.py, there's no physical RTSP camera available, so the
"running" path is proven with a real local video file (cv2's open/read logic doesn't
distinguish file paths from RTSP URLs internally).
"""
import time
import uuid

import cv2
import pytest
from ultralytics.utils import ASSETS

from app import tracking
from app.tracking import should_give_up

BUS_IMAGE = ASSETS / "bus.jpg"
UNREACHABLE_URL = "rtsp://127.0.0.1:1/does-not-exist"  # loopback, no listener -> fails fast


@pytest.fixture(autouse=True)
def cleanup_tracking_sessions():
    """Background tracking threads outlive a single test unless stopped explicitly —
    a leaked one would burn CPU and could skew timing in later tests (including in
    other files, e.g. test_camera_connection.py's timeout-regression test)."""
    yield
    tracking.tracking_manager.stop_all()


@pytest.fixture
def local_video(tmp_path):
    image = cv2.imread(str(BUS_IMAGE))
    height, width = image.shape[:2]
    video_path = tmp_path / "camera-feed.avi"
    writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"MJPG"), 5.0, (width, height))
    assert writer.isOpened()
    for _ in range(50):  # ~10s of processing headroom at the 5fps target rate
        writer.write(image)
    writer.release()
    return str(video_path)


def _create_camera(client, **overrides) -> dict:
    body = {"name": "Test camera", "rtsp_url": UNREACHABLE_URL}
    body.update(overrides)
    return client.post("/cameras", json=body).json()


def _wait_for_status(client, camera_id: str, target_statuses: list, timeout: float = 10) -> dict:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = client.get(f"/cameras/{camera_id}/tracking/status").json()
        if last["status"] in target_statuses:
            return last
        time.sleep(0.1)
    pytest.fail(f"status never reached {target_statuses}; last observed was {last}")


def _wait_for_first_frame(client, camera_id: str, timeout: float = 15) -> dict:
    # status flips to "running" as soon as the capture opens, before the first
    # model.track() call (which pays a one-off ~7s warm-up cost) actually completes —
    # so this polls for real progress (frame_count), not just the status label.
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = client.get(f"/cameras/{camera_id}/tracking/status").json()
        if last["status"] == "error":
            pytest.fail(f"tracking errored while waiting for the first frame: {last}")
        if last["frame_count"] >= 1:
            return last
        time.sleep(0.1)
    pytest.fail(f"no frame processed within {timeout}s; last observed was {last}")


class TestShouldGiveUp:
    def test_below_the_limit(self):
        assert should_give_up(0) is False
        assert should_give_up(tracking.MAX_RECONNECT_ATTEMPTS - 1) is False

    def test_at_or_above_the_limit(self):
        assert should_give_up(tracking.MAX_RECONNECT_ATTEMPTS) is True
        assert should_give_up(tracking.MAX_RECONNECT_ATTEMPTS + 1) is True


def test_reconnect_loop_gives_up_after_max_attempts_and_records_an_error(monkeypatch):
    # Exercises the real reconnect/give-up logic directly rather than via a full
    # start->EOF->reconnect thread cycle against a deleted file: on Windows, deleting a
    # video file while OpenCV might momentarily still hold it open is flaky
    # (PermissionError), so this is the robust way to test exhaustion deterministically.
    # MAX_RECONNECT_ATTEMPTS=1 keeps this fast: each real open attempt against an
    # unreachable address still takes the real ~5s OPEN_TIMEOUT_MS, unaffected by
    # RECONNECT_INTERVAL_SECONDS (that only shortens the wait *between* attempts).
    monkeypatch.setattr(tracking, "RECONNECT_INTERVAL_SECONDS", 0.02)
    monkeypatch.setattr(tracking, "MAX_RECONNECT_ATTEMPTS", 1)

    session = tracking.TrackingSession(uuid.uuid4(), UNREACHABLE_URL, None, None)
    result = session._reconnect_loop()

    assert result is None
    status = session.snapshot()
    assert status.status == "error"
    assert "reconnect" in status.error.lower()


def test_start_tracking_on_unreachable_camera_goes_straight_to_error(client):
    camera_id = _create_camera(client)["id"]

    response = client.post(f"/cameras/{camera_id}/tracking/start")
    assert response.status_code == 200

    status = _wait_for_status(client, camera_id, ["error"])
    assert status["error"]
    assert status["frame_count"] == 0


def test_start_tracking_on_a_real_stream_produces_running_frames_with_track_ids(client, local_video):
    camera_id = _create_camera(client, rtsp_url=local_video)["id"]

    assert client.post(f"/cameras/{camera_id}/tracking/start").status_code == 200

    status = _wait_for_first_frame(client, camera_id)
    assert status["status"] == "running"
    assert status["active_track_ids"], "bus.jpg has people in it — expected at least one active track"
    assert status["started_at"]
    assert status["last_frame_at"]

    frame_response = client.get(f"/cameras/{camera_id}/tracking/latest-frame")
    assert frame_response.status_code == 200
    assert frame_response.headers["content-type"] == "image/jpeg"
    assert frame_response.content[:2] == b"\xff\xd8"  # JPEG magic bytes

    stop_response = client.post(f"/cameras/{camera_id}/tracking/stop")
    assert stop_response.status_code == 200
    assert stop_response.json()["status"] == "stopped"
    assert client.get(f"/cameras/{camera_id}/tracking/status").json()["status"] == "stopped"


def test_starting_twice_reuses_the_existing_session_instead_of_restarting(client, local_video):
    camera_id = _create_camera(client, rtsp_url=local_video)["id"]
    first = client.post(f"/cameras/{camera_id}/tracking/start").json()
    _wait_for_status(client, camera_id, ["running"])

    second = client.post(f"/cameras/{camera_id}/tracking/start").json()

    assert second["started_at"] == first["started_at"]


def test_status_before_ever_starting_is_stopped(client):
    camera_id = _create_camera(client)["id"]
    assert client.get(f"/cameras/{camera_id}/tracking/status").json()["status"] == "stopped"


def test_stopping_a_camera_that_was_never_started_is_a_harmless_no_op(client):
    camera_id = _create_camera(client)["id"]
    response = client.post(f"/cameras/{camera_id}/tracking/stop")
    assert response.status_code == 200
    assert response.json()["status"] == "stopped"


def test_latest_frame_404s_before_tracking_has_ever_started(client):
    camera_id = _create_camera(client)["id"]
    response = client.get(f"/cameras/{camera_id}/tracking/latest-frame")
    assert response.status_code == 404


def test_latest_frame_503s_while_starting_up_before_the_first_frame(client, local_video):
    camera_id = _create_camera(client, rtsp_url=local_video)["id"]
    client.post(f"/cameras/{camera_id}/tracking/start")

    response = client.get(f"/cameras/{camera_id}/tracking/latest-frame")

    assert response.status_code in (200, 503)


@pytest.mark.parametrize("endpoint", ["start", "stop", "status", "latest-frame"])
def test_tracking_endpoints_404_for_an_unknown_camera(client, endpoint):
    method = client.post if endpoint in ("start", "stop") else client.get
    response = method(f"/cameras/{uuid.uuid4()}/tracking/{endpoint}")
    assert response.status_code == 404
