"""cloud-engine's own coverage. backend/tests already exhaustively proves the tracking/
counting/zone/heatmap/scanning logic itself is correct (it's the same app/tracking.py
code, imported directly — see main.py's module docstring); these tests instead prove
cloud-engine's own thin layer on top of it: the internal-secret auth gate, the
camera-must-belong-to-a-vero_cloud-organization check, and that a real tracking session
started through *this* service's own endpoints genuinely runs and produces a real count.
No mocked AI — this drives real YOLO+ByteTrack over the same panning_video fixture
backend's own real-tracking test uses.
"""
import time
import uuid


class TestHealth:
    def test_health_needs_no_auth(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestInternalSecretAuth:
    def test_missing_secret_is_rejected(self, client, vero_cloud_camera):
        response = client.post(f"/cameras/{vero_cloud_camera.id}/tracking/stop")
        assert response.status_code == 401

    def test_wrong_secret_is_rejected(self, client, vero_cloud_camera):
        response = client.get(
            f"/cameras/{vero_cloud_camera.id}/tracking/status",
            headers={"X-Internal-Secret": "the-wrong-secret"},
        )
        assert response.status_code == 401

    def test_correct_secret_is_accepted(self, client, vero_cloud_camera, internal_secret):
        response = client.get(
            f"/cameras/{vero_cloud_camera.id}/tracking/status",
            headers={"X-Internal-Secret": internal_secret},
        )
        assert response.status_code == 200


class TestCameraResolution:
    def test_a_camera_id_that_is_not_a_uuid_is_404(self, client, internal_secret):
        response = client.get(
            "/cameras/not-a-uuid/tracking/status", headers={"X-Internal-Secret": internal_secret}
        )
        assert response.status_code == 404

    def test_an_unknown_camera_id_is_404(self, client, internal_secret):
        response = client.get(
            f"/cameras/{uuid.uuid4()}/tracking/status", headers={"X-Internal-Secret": internal_secret}
        )
        assert response.status_code == 404

    def test_a_camera_whose_organization_is_not_on_vero_cloud_is_403(
        self, client, own_hardware_camera, internal_secret
    ):
        response = client.get(
            f"/cameras/{own_hardware_camera.id}/tracking/status", headers={"X-Internal-Secret": internal_secret}
        )
        assert response.status_code == 403


class TestRealTrackingLifecycle:
    def test_a_real_tracked_person_crossing_a_real_line_increments_a_real_count(
        self, client, db_session, vero_cloud_camera, panning_video, internal_secret
    ):
        from app.models import Line

        video_path, width, _height = panning_video
        # Same verified-by-hand crossing point as backend's own equivalent test
        # (backend/tests/test_tracking_counting.py) — same video, same math.
        line_x_fraction = 300 / width
        vero_cloud_camera.rtsp_url = video_path
        db_session.add(
            Line(
                camera_id=vero_cloud_camera.id,
                name="Midline",
                x1=line_x_fraction,
                y1=0.0,
                x2=line_x_fraction,
                y2=1.0,
            )
        )
        db_session.commit()

        headers = {"X-Internal-Secret": internal_secret}
        start = client.post(f"/cameras/{vero_cloud_camera.id}/tracking/start", headers=headers)
        assert start.status_code == 200, start.text

        deadline = time.monotonic() + 30
        status = None
        try:
            while time.monotonic() < deadline:
                status = client.get(f"/cameras/{vero_cloud_camera.id}/tracking/status", headers=headers).json()
                if status["status"] == "error":
                    raise AssertionError(f"tracking errored: {status}")
                counts = status["line_counts"][0] if status["line_counts"] else None
                if counts and (counts["in_count"] + counts["out_count"]) > 0:
                    break
                time.sleep(0.2)
            else:
                raise AssertionError(f"no crossing detected within 30s; last status: {status}")

            frame_response = client.get(
                f"/cameras/{vero_cloud_camera.id}/tracking/latest-frame", headers=headers
            )
            assert frame_response.status_code == 200
            assert frame_response.headers["content-type"] == "image/jpeg"
            assert len(frame_response.content) > 0
        finally:
            client.post(f"/cameras/{vero_cloud_camera.id}/tracking/stop", headers=headers)

        counts = status["line_counts"][0]
        assert counts["name"] == "Midline"
        assert counts["in_count"] + counts["out_count"] >= 1

    def test_stop_on_a_session_that_was_never_started_is_a_no_op(self, client, vero_cloud_camera, internal_secret):
        response = client.post(
            f"/cameras/{vero_cloud_camera.id}/tracking/stop", headers={"X-Internal-Secret": internal_secret}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "stopped"

    def test_latest_frame_before_tracking_started_is_404(self, client, vero_cloud_camera, internal_secret):
        response = client.get(
            f"/cameras/{vero_cloud_camera.id}/tracking/latest-frame", headers={"X-Internal-Secret": internal_secret}
        )
        assert response.status_code == 404


class TestCameraEndpoints:
    def test_test_connection_against_an_unreachable_camera_reports_offline(
        self, client, vero_cloud_camera, internal_secret
    ):
        response = client.post(
            f"/cameras/{vero_cloud_camera.id}/test-connection", headers={"X-Internal-Secret": internal_secret}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["connection_status"] == "offline"
        assert body["last_error"]

    def test_snapshot_against_an_unreachable_camera_is_503(self, client, vero_cloud_camera, internal_secret):
        response = client.get(
            f"/cameras/{vero_cloud_camera.id}/snapshot", headers={"X-Internal-Secret": internal_secret}
        )
        assert response.status_code == 503
