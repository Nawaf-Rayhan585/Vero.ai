"""Connection-test and snapshot behavior. Real OpenCV, real PostgreSQL, no mocks.

There is no physical RTSP camera available to test against here, so the "online" path
is proven with a real local video file — cv2's open/read logic doesn't distinguish
file paths from RTSP URLs internally, so this genuinely exercises the same code path.
Actual RTSP-specific behavior (auth negotiation, codecs, camera quirks) is NOT verified
by these tests and needs a real camera on the owner's network.
"""
import time
import uuid

import cv2
import pytest
from ultralytics.utils import ASSETS

from app import camera_testing
from app.camera_testing import build_stream_url
from app.models import Camera

BUS_IMAGE = ASSETS / "bus.jpg"
UNREACHABLE_URL = "rtsp://127.0.0.1:1/does-not-exist"  # loopback, no listener -> fails fast


@pytest.fixture
def local_video(tmp_path):
    image = cv2.imread(str(BUS_IMAGE))
    height, width = image.shape[:2]
    video_path = tmp_path / "camera-feed.avi"
    writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"MJPG"), 5.0, (width, height))
    assert writer.isOpened()
    for _ in range(3):
        writer.write(image)
    writer.release()
    return str(video_path)


def _create_camera(client, **overrides):
    body = {"name": "Test camera", "rtsp_url": UNREACHABLE_URL}
    body.update(overrides)
    return client.post("/cameras", json=body).json()


def test_build_stream_url_embeds_username_and_password():
    url = build_stream_url("rtsp://192.0.2.1:554/stream1", "admin", "p@ss/w:ord")
    assert url == "rtsp://admin:p%40ss%2Fw%3Aord@192.0.2.1:554/stream1"


def test_build_stream_url_without_username_is_unchanged():
    assert build_stream_url("rtsp://192.0.2.1:554/stream1", None, "irrelevant") == "rtsp://192.0.2.1:554/stream1"


def test_connection_to_an_unreachable_address_reports_offline_with_an_error():
    outcome = camera_testing.test_connection(UNREACHABLE_URL)
    assert outcome.online is False
    assert outcome.error


def test_unreachable_connection_fails_within_the_configured_open_timeout_not_opencvs_30s_default():
    # Regression guard: cv2.VideoCapture() + .set(...) + .open(...) silently ignores
    # CAP_PROP_OPEN_TIMEOUT_MSEC and falls back to OpenCV's own ~30s default — only the
    # cv2.VideoCapture(url, backend, [prop, value, ...]) constructor form honors it
    # (confirmed empirically). This was caught because it made the whole suite slow.
    started = time.monotonic()
    camera_testing.test_connection(UNREACHABLE_URL)
    elapsed = time.monotonic() - started
    assert elapsed < camera_testing.HARD_TIMEOUT_SECONDS, (
        f"took {elapsed:.1f}s — timeout property is probably being silently ignored again"
    )


def test_connection_to_a_real_readable_stream_reports_online_with_metadata(local_video):
    outcome = camera_testing.test_connection(local_video)
    assert outcome.online is True
    assert outcome.error is None
    assert outcome.width and outcome.height
    assert outcome.fps


def test_test_connection_endpoint_persists_offline_result(client, db_session):
    camera_id = _create_camera(client)["id"]

    response = client.post(f"/cameras/{camera_id}/test-connection")

    assert response.status_code == 200
    body = response.json()
    assert body["connection_status"] == "offline"
    assert body["last_error"]
    assert body["last_tested_at"]

    row = db_session.get(Camera, uuid.UUID(camera_id))
    assert row.connection_status == "offline"


def test_test_connection_endpoint_persists_online_result_with_resolution(client, local_video):
    camera_id = _create_camera(client, rtsp_url=local_video)["id"]

    body = client.post(f"/cameras/{camera_id}/test-connection").json()

    assert body["connection_status"] == "online"
    assert body["last_error"] is None
    assert body["last_width"] and body["last_height"]


def test_snapshot_returns_a_real_jpeg_for_a_reachable_source(client, local_video):
    camera_id = _create_camera(client, rtsp_url=local_video)["id"]

    response = client.get(f"/cameras/{camera_id}/snapshot")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content[:2] == b"\xff\xd8"  # JPEG magic bytes
    assert len(response.content) > 100


def test_snapshot_returns_503_for_an_unreachable_camera(client):
    camera_id = _create_camera(client)["id"]

    response = client.get(f"/cameras/{camera_id}/snapshot")

    assert response.status_code == 503
    assert response.json()["detail"]
