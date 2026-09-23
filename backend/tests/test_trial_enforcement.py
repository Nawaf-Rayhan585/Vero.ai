"""What an expired trial (no active subscription) actually blocks: creating or growing
usage, and nothing else. Existing data stays readable, and every action that *reduces*
usage — delete anything, stop tracking, remove/leave a member — keeps working."""
import pytest


@pytest.fixture
def expired_scenario(client, register_user, add_member, panning_video):
    """A fully set-up organization (camera, line, zone, a second location, a second
    member) whose trial is then expired — built *before* expiring it, since creating
    this scaffolding itself goes through the same growth gate being tested."""
    video_path, _width, _height = panning_video
    camera = client.post("/cameras", json={"name": "Front door", "rtsp_url": video_path}).json()
    line = client.post(
        f"/cameras/{camera['id']}/lines", json={"name": "Kerb", "x1": 0.5, "y1": 0.0, "x2": 0.5, "y2": 1.0}
    ).json()
    zone = client.post(
        f"/cameras/{camera['id']}/zones",
        json={"name": "Floor", "points": [{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 1, "y": 1}, {"x": 0, "y": 1}]},
    ).json()
    location = client.post("/locations", json={"name": "Warehouse"}).json()
    member_client = register_user("member@example.com")
    member = add_member(client, member_client, role="member")

    client.patch("/subscription", json={"status": "expired"})

    from types import SimpleNamespace

    return SimpleNamespace(camera=camera, line=line, zone=zone, location=location, member=member)


class TestGrowthActionsAreBlocked:
    """Every endpoint that creates something new, or edits an existing camera/location,
    gated by require_active_configurator (app/auth.py)."""

    def test_creating_a_camera_is_blocked(self, client, expired_scenario):
        response = client.post("/cameras", json={"name": "New cam", "rtsp_url": "rtsp://x/y"})
        assert response.status_code == 402

    def test_editing_a_camera_is_blocked(self, client, expired_scenario):
        response = client.patch(f"/cameras/{expired_scenario.camera['id']}", json={"name": "Renamed"})
        assert response.status_code == 402

    def test_creating_a_line_is_blocked(self, client, expired_scenario):
        response = client.post(
            f"/cameras/{expired_scenario.camera['id']}/lines",
            json={"name": "Another", "x1": 0, "y1": 0, "x2": 1, "y2": 1},
        )
        assert response.status_code == 402

    def test_creating_a_zone_is_blocked(self, client, expired_scenario):
        square = [{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 1, "y": 1}, {"x": 0, "y": 1}]
        response = client.post(f"/cameras/{expired_scenario.camera['id']}/zones", json={"name": "x", "points": square})
        assert response.status_code == 402

    def test_creating_a_location_is_blocked(self, client, expired_scenario):
        assert client.post("/locations", json={"name": "Storefront"}).status_code == 402

    def test_renaming_a_location_is_blocked(self, client, expired_scenario):
        response = client.patch(f"/locations/{expired_scenario.location['id']}", json={"name": "Renamed"})
        assert response.status_code == 402

    def test_adding_a_member_is_blocked(self, client, expired_scenario):
        response = client.post("/members", json={"email": "nobody@example.com", "role": "member"})
        assert response.status_code == 402

    def test_changing_a_members_role_is_blocked(self, client, expired_scenario):
        response = client.patch(f"/members/{expired_scenario.member['user_id']}", json={"role": "admin"})
        assert response.status_code == 402

    def test_starting_tracking_is_blocked(self, client, expired_scenario):
        response = client.post(f"/cameras/{expired_scenario.camera['id']}/tracking/start")
        assert response.status_code == 402

    def test_the_error_message_points_at_the_subscription_page(self, client, expired_scenario):
        response = client.post("/cameras", json={"name": "x", "rtsp_url": "rtsp://x/y"})
        assert "trial" in response.json()["detail"].lower()


class TestShrinkActionsStayAllowed:
    """Deleting, stopping, and leaving/removing keep working on an expired trial —
    require_configurator (no subscription check), unchanged from Phase 10."""

    def test_deleting_a_camera_still_works(self, client, expired_scenario):
        assert client.delete(f"/cameras/{expired_scenario.camera['id']}").status_code == 204

    def test_deleting_a_line_still_works(self, client, expired_scenario):
        assert client.delete(f"/lines/{expired_scenario.line['id']}").status_code == 204

    def test_deleting_a_zone_still_works(self, client, expired_scenario):
        assert client.delete(f"/zones/{expired_scenario.zone['id']}").status_code == 204

    def test_deleting_an_empty_location_still_works(self, client, expired_scenario):
        assert client.delete(f"/locations/{expired_scenario.location['id']}").status_code == 204

    def test_stopping_tracking_still_works(self, client, expired_scenario):
        response = client.post(f"/cameras/{expired_scenario.camera['id']}/tracking/stop")
        assert response.status_code == 200

    def test_removing_a_member_still_works(self, client, expired_scenario):
        response = client.delete(f"/members/{expired_scenario.member['user_id']}")
        assert response.status_code == 204

    def test_a_member_can_still_leave_on_their_own(self, client, register_user, add_member):
        member_client = register_user("leaver@example.com")
        member = add_member(client, member_client, role="member")
        client.patch("/subscription", json={"status": "expired"})

        response = member_client.delete(f"/members/{member['user_id']}")

        assert response.status_code == 204

    def test_renaming_the_organization_still_works(self, client, expired_scenario):
        response = client.patch(f"/organizations/{client.test_organization['id']}", json={"name": "Renamed Org"})
        assert response.status_code == 200

    def test_creating_another_organization_still_works(self, client, expired_scenario):
        # A new organization gets its own fresh trial - unrelated to this one's billing.
        response = client.post("/organizations", json={"name": "Org B"})
        assert response.status_code == 200

    def test_testing_a_cameras_connection_still_works(self, client, expired_scenario):
        response = client.post(f"/cameras/{expired_scenario.camera['id']}/test-connection")
        assert response.status_code == 200


class TestReadsStayUnaffected:
    def test_listing_cameras_still_works(self, client, expired_scenario):
        assert client.get("/cameras").status_code == 200

    def test_listing_events_still_works(self, client, expired_scenario):
        assert client.get("/events").status_code == 200

    def test_analytics_summary_still_works(self, client, expired_scenario):
        response = client.get("/analytics/summary", params={"since": "2026-01-01T00:00:00Z"})
        assert response.status_code == 200

    def test_listing_locations_still_works(self, client, expired_scenario):
        assert client.get("/locations").status_code == 200

    def test_listing_members_still_works(self, client, expired_scenario):
        assert client.get("/members").status_code == 200

    def test_me_still_works(self, client, expired_scenario):
        assert client.get("/auth/me").status_code == 200

    def test_tracking_status_is_still_readable(self, client, expired_scenario):
        response = client.get(f"/cameras/{expired_scenario.camera['id']}/tracking/status")
        assert response.status_code == 200


class TestCameraEntitlementLimit:
    """The entitlement mechanism (max_cameras) — real code, but nothing sets it on any
    real organization in Phase 11, so this proves it works using a subscription forced
    into a limit directly, not anything a real registration flow can reach."""

    def test_creating_a_camera_beyond_max_cameras_is_blocked(self, client, db_session):
        from app.models import Subscription

        sub = db_session.query(Subscription).filter_by(organization_id=client.test_organization["id"]).one()
        sub.max_cameras = 1
        db_session.commit()

        first = client.post("/cameras", json={"name": "cam-1", "rtsp_url": "rtsp://x/y"})
        assert first.status_code == 200

        second = client.post("/cameras", json={"name": "cam-2", "rtsp_url": "rtsp://x/y"})
        assert second.status_code == 402
        assert "1 camera" in second.json()["detail"]

    def test_unlimited_by_default(self, client):
        for i in range(3):
            response = client.post("/cameras", json={"name": f"cam-{i}", "rtsp_url": "rtsp://x/y"})
            assert response.status_code == 200
