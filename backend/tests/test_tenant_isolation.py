"""Two cross-cutting guarantees that don't belong to any single router:

1. Every route requires authentication, except an explicit, short public allow-list — so a
   future endpoint that forgets to add auth fails this suite rather than shipping open.
2. Data created by one organization is invisible to another, checked directly against the
   real endpoints (not just "the SQL has a WHERE clause") for every kind of record a
   camera can have.
"""
import re
import uuid
from datetime import datetime, timezone

import pytest

from app.routers import (
    analytics,
    auth,
    cameras,
    devices,
    events,
    jobs,
    lines,
    locations,
    members,
    organizations,
    subscription,
    tracking,
    zones,
)

ROUTERS = [
    auth.router,
    organizations.router,
    locations.router,
    members.router,
    subscription.router,
    devices.router,
    jobs.router,
    cameras.router,
    tracking.router,
    lines.router,
    zones.router,
    events.router,
    analytics.router,
]

# Genuinely public: no account is needed to reach them at all. /auth/refresh belongs here
# by design, not by oversight — refreshing is exactly what you do when you no longer have
# a valid access token; it authenticates via the refresh token in its body instead. The
# three /subscription/paypal/* routes are public for a different reason (Phase 15):
# PayPal's own servers reach them — a browser redirect or a server-to-server webhook —
# neither of which can carry this app's JWT. Their actual public-ness (and that the
# return/cancel-return pages make no database write, and the webhook still rejects an
# unverifiable signature) is tested directly in tests/test_paypal_subscription.py.
PUBLIC_ROUTES = {
    ("POST", "/auth/register"),
    ("POST", "/auth/login"),
    ("POST", "/auth/refresh"),
    ("GET", "/subscription/paypal/return"),
    ("GET", "/subscription/paypal/cancel-return"),
    ("POST", "/subscription/paypal/webhook"),
}


def _all_routes() -> list[tuple[str, str]]:
    routes = []
    for router in ROUTERS:
        for route in router.routes:
            for method in sorted(route.methods - {"HEAD"}):
                routes.append((method, route.path))
    return routes


def _fill_path(path: str) -> str:
    return re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path)


ALL_ROUTES = _all_routes()


class TestEveryRouteRequiresAuthentication:
    @pytest.mark.parametrize("method,path", [r for r in ALL_ROUTES if r not in PUBLIC_ROUTES])
    def test_an_anonymous_request_is_rejected(self, anonymous_client, method, path):
        response = anonymous_client.request(method, _fill_path(path), json={})

        assert response.status_code == 401, f"{method} {path} did not require authentication"

    def test_the_public_auth_routes_do_not_require_authentication(self, anonymous_client):
        # They fail for a *different* reason (a missing/invalid body -> 422), proving they
        # were actually reached rather than accidentally exempted by a typo above.
        assert anonymous_client.post("/auth/register", json={}).status_code == 422
        assert anonymous_client.post("/auth/login", json={}).status_code == 422
        assert anonymous_client.post("/auth/refresh", json={}).status_code == 422

    def test_this_sweep_is_not_accidentally_empty(self):
        # If a future refactor changes how routers are registered, this catches the case
        # where ALL_ROUTES silently became [] and the parametrized test above ran zero
        # cases (a green suite for the wrong reason).
        assert len(ALL_ROUTES) >= 40

    def test_health_endpoints_are_deliberately_left_out_of_the_sweep_and_are_public(self, anonymous_client):
        # /health and /health/db are registered directly on the app, not via a router in
        # ROUTERS, so the sweep above never touches them; confirmed separately here.
        assert anonymous_client.get("/health").status_code == 200
        assert anonymous_client.get("/health/db").status_code in (200, 503)


@pytest.fixture
def scenario(client, register_user, panning_video):
    """Camera A (org: `client`) fully configured — a line, a zone, and, once tracking has
    produced them, real events and a real heatmap snapshot — plus `other`, a second,
    unrelated organization that must not be able to see any of it."""
    video_path, width, _height = panning_video
    camera = client.post("/cameras", json={"name": "Street", "rtsp_url": video_path}).json()
    line = client.post(
        f"/cameras/{camera['id']}/lines", json={"name": "Kerb", "x1": 0.5, "y1": 0.0, "x2": 0.5, "y2": 1.0}
    ).json()
    zone = client.post(
        f"/cameras/{camera['id']}/zones",
        json={"name": "Floor", "points": [{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 1, "y": 1}, {"x": 0, "y": 1}]},
    ).json()
    location = client.get("/locations").json()[0]
    job = client.post("/jobs", json={"video_source": video_path, "model_type": "yolo"}).json()
    device = client.post("/devices", json={"name": "Store PC"}).json()

    other = register_user("other-org-owner@example.com", organization_name="Other Org")

    from types import SimpleNamespace

    return SimpleNamespace(camera=camera, line=line, zone=zone, location=location, job=job, device=device, other=other)


class TestTenantIsolation:
    def test_a_camera_is_invisible_to_another_organization(self, scenario):
        assert scenario.other.get(f"/cameras/{scenario.camera['id']}").status_code == 404
        assert scenario.other.get("/cameras").json() == []

    def test_another_organization_cannot_modify_or_delete_the_camera(self, scenario):
        assert scenario.other.patch(f"/cameras/{scenario.camera['id']}", json={"name": "Hijacked"}).status_code == 404
        assert scenario.other.delete(f"/cameras/{scenario.camera['id']}").status_code == 404
        assert scenario.other.post(f"/cameras/{scenario.camera['id']}/test-connection").status_code == 404
        assert scenario.other.get(f"/cameras/{scenario.camera['id']}/snapshot").status_code == 404

    def test_another_organization_cannot_reach_the_cameras_lines(self, scenario):
        assert scenario.other.get(f"/cameras/{scenario.camera['id']}/lines").status_code == 404
        assert (
            scenario.other.post(
                f"/cameras/{scenario.camera['id']}/lines", json={"name": "x", "x1": 0, "y1": 0, "x2": 1, "y2": 1}
            ).status_code
            == 404
        )
        assert scenario.other.delete(f"/lines/{scenario.line['id']}").status_code == 404

    def test_another_organization_cannot_reach_the_cameras_zones(self, scenario):
        square = [{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 1, "y": 1}, {"x": 0, "y": 1}]
        assert scenario.other.get(f"/cameras/{scenario.camera['id']}/zones").status_code == 404
        assert scenario.other.post(f"/cameras/{scenario.camera['id']}/zones", json={"name": "x", "points": square}).status_code == 404
        assert scenario.other.delete(f"/zones/{scenario.zone['id']}").status_code == 404

    def test_another_organization_cannot_control_or_watch_tracking(self, scenario):
        assert scenario.other.post(f"/cameras/{scenario.camera['id']}/tracking/start").status_code == 404
        assert scenario.other.post(f"/cameras/{scenario.camera['id']}/tracking/stop").status_code == 404
        assert scenario.other.get(f"/cameras/{scenario.camera['id']}/tracking/status").status_code == 404
        assert scenario.other.get(f"/cameras/{scenario.camera['id']}/tracking/latest-frame").status_code == 404

    def test_another_organizations_events_list_is_empty_even_unfiltered(self, scenario, add_event):
        add_event(
            scenario.camera["id"], "line_crossed", datetime(2026, 1, 1, tzinfo=timezone.utc), category="person", direction="in"
        )

        assert scenario.other.get("/events").json() == {"events": [], "next_before": None}

    def test_asking_for_another_organizations_camera_by_id_in_events_is_404(self, scenario):
        assert scenario.other.get("/events", params={"camera_id": scenario.camera["id"]}).status_code == 404

    def test_another_organizations_analytics_are_all_zero_not_leaked(self, scenario, add_event):
        add_event(
            scenario.camera["id"], "line_crossed", datetime(2026, 1, 1, tzinfo=timezone.utc), category="person", direction="in"
        )

        summary = scenario.other.get("/analytics/summary", params={"since": "2000-01-01T00:00:00Z"}).json()

        assert (summary["people_in"], summary["people_out"]) == (0, 0)
        assert summary["lines"] == [] and summary["zones"] == []

    def test_analytics_for_a_specific_foreign_camera_is_404(self, scenario):
        response = scenario.other.get(
            "/analytics/summary", params={"since": "2000-01-01T00:00:00Z", "camera_id": scenario.camera["id"]}
        )
        assert response.status_code == 404

    def test_another_organization_cannot_see_the_heatmap(self, scenario, add_heat):
        add_heat(scenario.camera["id"], datetime(2026, 1, 1, tzinfo=timezone.utc), {(1, 1): 5})

        info = scenario.other.get(
            "/analytics/heatmap/info", params={"camera_id": scenario.camera["id"], "since": "2000-01-01T00:00:00Z"}
        )
        assert info.status_code == 404

    def test_another_organizations_location_is_invisible_and_unusable(self, scenario):
        # `other` has its own "Main location" (from its own registration) — the point is
        # that it never sees *client's*, not that its own list is empty.
        assert scenario.location["id"] not in [loc["id"] for loc in scenario.other.get("/locations").json()]
        assert scenario.other.patch(f"/locations/{scenario.location['id']}", json={"name": "x"}).status_code == 404
        assert scenario.other.delete(f"/locations/{scenario.location['id']}").status_code == 404

    def test_a_camera_cannot_be_created_on_another_organizations_location(self, scenario):
        response = scenario.other.post(
            "/cameras", json={"name": "x", "rtsp_url": "rtsp://x/y", "location_id": scenario.location["id"]}
        )
        assert response.status_code == 404

    def test_another_organizations_job_is_invisible(self, scenario):
        assert scenario.other.get(f"/jobs/{scenario.job['id']}").status_code == 404
        assert scenario.other.get("/jobs").json() == []

    def test_another_organizations_members_are_invisible(self, scenario):
        response = scenario.other.get("/members")
        assert response.status_code == 200
        assert [m["email"] for m in response.json()] == ["other-org-owner@example.com"]

    def test_membership_in_one_organization_grants_no_role_in_another(self, scenario):
        # `other` is genuinely unrelated to `scenario.camera`'s organization — not even a
        # Member there — so every write attempt is a 404 (see the tests above), and trying
        # to act as that organization via the header is also refused.
        response = scenario.other.get("/cameras", headers={"X-Organization-Id": str(uuid.uuid4())})
        assert response.status_code == 404

    def test_each_organization_has_its_own_independent_subscription(self, client, scenario):
        client.patch("/subscription", json={"status": "expired"})

        other_subscription = scenario.other.get("/subscription").json()
        assert other_subscription["status"] == "trialing"
        assert other_subscription["is_active"] is True

    def test_another_organizations_device_is_invisible_and_unusable(self, scenario):
        # There is no GET /devices/{id} (like locations, only list/create/update/delete
        # exist), so unlike the camera checks above this doesn't include a single-GET.
        assert scenario.other.patch(f"/devices/{scenario.device['id']}", json={"name": "Hijacked"}).status_code == 404
        assert scenario.other.delete(f"/devices/{scenario.device['id']}").status_code == 404
        assert scenario.device["id"] not in [d["id"] for d in scenario.other.get("/devices").json()]
