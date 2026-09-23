"""Phase 13: backend proxies camera-processing requests to cloud-engine for
organizations on the "vero_cloud" plan, and leaves every other organization on the
existing local tracking_manager path untouched. Every other existing test in this suite
(none of which sets plan_type) is itself proof the local path is unaffected by this
change; these tests cover only the new cloud branch, mocking cloud-engine's HTTP
response so no second service needs to actually be running."""
from unittest.mock import Mock, patch

import pytest


class FakeSettings:
    def __init__(self, base_url="http://cloud-engine.test", secret="s3cr3t"):
        self.cloud_engine_base_url = base_url
        self.cloud_engine_internal_secret = secret


def _mock_response(status_code=200, json_body=None, content=b"", headers=None):
    response = Mock()
    response.status_code = status_code
    response.json.return_value = json_body if json_body is not None else {}
    response.text = ""
    response.content = content
    response.headers = headers or {}
    return response


_STOPPED = {
    "status": "stopped",
    "error": None,
    "frame_count": 0,
    "started_at": None,
    "last_frame_at": None,
    "active_track_ids": [],
    "active_vehicle_track_ids": [],
    "line_counts": [],
    "zone_counts": [],
    "reads": [],
}


@pytest.fixture
def cloud_client(client):
    """`client`'s own organization, switched onto the Vero Cloud plan."""
    response = client.patch("/subscription", json={"plan_type": "vero_cloud"})
    assert response.status_code == 200, response.text
    return client


@pytest.fixture
def cloud_camera(cloud_client):
    return cloud_client.post("/cameras", json={"name": "Cam", "rtsp_url": "rtsp://x/y"}).json()


class TestTrackingIsProxied:
    def test_start_tracking_calls_cloud_engine_with_the_internal_secret(self, cloud_client, cloud_camera):
        running = {**_STOPPED, "status": "running", "frame_count": 1}
        with (
            patch("app.cloud_routing.get_settings", return_value=FakeSettings()),
            patch("app.cloud_routing.httpx.request", return_value=_mock_response(200, running)) as mock_request,
        ):
            response = cloud_client.post(f"/cameras/{cloud_camera['id']}/tracking/start")

        assert response.status_code == 200
        assert response.json()["status"] == "running"
        method, url = mock_request.call_args.args
        assert method == "POST"
        assert url == f"http://cloud-engine.test/cameras/{cloud_camera['id']}/tracking/start"
        assert mock_request.call_args.kwargs["headers"]["X-Internal-Secret"] == "s3cr3t"

    def test_a_cloud_engine_error_is_relayed_with_its_own_status_and_detail(self, cloud_client, cloud_camera):
        with (
            patch("app.cloud_routing.get_settings", return_value=FakeSettings()),
            patch(
                "app.cloud_routing.httpx.request",
                return_value=_mock_response(422, {"detail": "Enable at least one AI module first"}),
            ),
        ):
            response = cloud_client.post(f"/cameras/{cloud_camera['id']}/tracking/start")

        assert response.status_code == 422
        assert "Enable at least one" in response.json()["detail"]

    def test_returns_503_when_cloud_engine_is_not_configured(self, cloud_client, cloud_camera):
        with patch("app.cloud_routing.get_settings", return_value=FakeSettings(base_url=None, secret=None)):
            response = cloud_client.post(f"/cameras/{cloud_camera['id']}/tracking/start")

        assert response.status_code == 503

    def test_returns_503_when_cloud_engine_is_unreachable(self, cloud_client, cloud_camera):
        import httpx

        with (
            patch("app.cloud_routing.get_settings", return_value=FakeSettings()),
            patch("app.cloud_routing.httpx.request", side_effect=httpx.ConnectError("refused")),
        ):
            response = cloud_client.post(f"/cameras/{cloud_camera['id']}/tracking/start")

        assert response.status_code == 503

    def test_stop_is_proxied(self, cloud_client, cloud_camera):
        with (
            patch("app.cloud_routing.get_settings", return_value=FakeSettings()),
            patch("app.cloud_routing.httpx.request", return_value=_mock_response(200, _STOPPED)) as mock_request,
        ):
            response = cloud_client.post(f"/cameras/{cloud_camera['id']}/tracking/stop")

        assert response.status_code == 200
        assert mock_request.call_args.args[1].endswith(f"/cameras/{cloud_camera['id']}/tracking/stop")

    def test_status_is_proxied(self, cloud_client, cloud_camera):
        with (
            patch("app.cloud_routing.get_settings", return_value=FakeSettings()),
            patch("app.cloud_routing.httpx.request", return_value=_mock_response(200, _STOPPED)) as mock_request,
        ):
            response = cloud_client.get(f"/cameras/{cloud_camera['id']}/tracking/status")

        assert response.status_code == 200
        assert mock_request.call_args.args[1].endswith(f"/cameras/{cloud_camera['id']}/tracking/status")

    def test_latest_frame_is_proxied_and_relays_raw_bytes_with_the_heatmap_flag(self, cloud_client, cloud_camera):
        jpeg_bytes = b"\xff\xd8fake-jpeg"
        with (
            patch("app.cloud_routing.get_settings", return_value=FakeSettings()),
            patch(
                "app.cloud_routing.httpx.request",
                return_value=_mock_response(200, content=jpeg_bytes, headers={"content-type": "image/jpeg"}),
            ) as mock_request,
        ):
            response = cloud_client.get(f"/cameras/{cloud_camera['id']}/tracking/latest-frame?heatmap=true")

        assert response.status_code == 200
        assert response.content == jpeg_bytes
        assert response.headers["content-type"] == "image/jpeg"
        assert mock_request.call_args.kwargs["params"] == {"heatmap": True}


class TestCameraEndpointsAreProxied:
    def test_test_connection_is_proxied(self, cloud_client, cloud_camera):
        camera_body = {**cloud_camera, "connection_status": "online"}
        with (
            patch("app.cloud_routing.get_settings", return_value=FakeSettings()),
            patch("app.cloud_routing.httpx.request", return_value=_mock_response(200, camera_body)) as mock_request,
        ):
            response = cloud_client.post(f"/cameras/{cloud_camera['id']}/test-connection")

        assert response.status_code == 200
        assert response.json()["connection_status"] == "online"
        assert mock_request.call_args.args[1].endswith("/test-connection")

    def test_snapshot_is_proxied_and_relays_raw_bytes(self, cloud_client, cloud_camera):
        jpeg_bytes = b"\xff\xd8fake-jpeg"
        with (
            patch("app.cloud_routing.get_settings", return_value=FakeSettings()),
            patch(
                "app.cloud_routing.httpx.request",
                return_value=_mock_response(200, content=jpeg_bytes, headers={"content-type": "image/jpeg"}),
            ),
        ):
            response = cloud_client.get(f"/cameras/{cloud_camera['id']}/snapshot")

        assert response.status_code == 200
        assert response.content == jpeg_bytes


class TestOrganizationsWithoutTheCloudPlanAreUnaffected:
    def test_a_plain_organization_never_calls_cloud_engine(self, client):
        # plan_type is unset by default (Phase 11) — this must never reach cloud_routing
        # at all, let alone make an HTTP call.
        camera = client.post("/cameras", json={"name": "Cam", "rtsp_url": "rtsp://x/y"}).json()
        with patch("app.cloud_routing.httpx.request") as mock_request:
            response = client.post(f"/cameras/{camera['id']}/tracking/stop")

        mock_request.assert_not_called()
        assert response.status_code == 200

    def test_an_own_hardware_organization_never_calls_cloud_engine(self, client):
        client.patch("/subscription", json={"plan_type": "own_hardware"})
        camera = client.post("/cameras", json={"name": "Cam", "rtsp_url": "rtsp://x/y"}).json()
        with patch("app.cloud_routing.httpx.request") as mock_request:
            response = client.post(f"/cameras/{camera['id']}/test-connection")

        mock_request.assert_not_called()
        # Still runs the real local connection test — this rtsp_url is unreachable, so it
        # completes (not a proxy 503) and reports offline, proving the local path ran.
        assert response.status_code == 200
        assert response.json()["connection_status"] == "offline"
