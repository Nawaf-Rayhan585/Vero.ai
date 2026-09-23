"""Locations: CRUD, the default location every organization starts with, the delete-blocked
-while-it-has-cameras rule, and role/tenant scoping."""
import uuid


def _create_camera(client, location_id=None, **overrides):
    body = {"name": "Front door", "rtsp_url": "rtsp://x/y"}
    if location_id is not None:
        body["location_id"] = location_id
    body.update(overrides)
    return client.post("/cameras", json=body).json()


class TestListAndCreate:
    def test_a_fresh_organization_has_one_default_location(self, client):
        locations = client.get("/locations").json()

        assert len(locations) == 1
        assert locations[0]["name"] == "Main location"
        assert locations[0]["timezone"] == "UTC"
        assert locations[0]["camera_count"] == 0

    def test_creating_a_location(self, client):
        response = client.post("/locations", json={"name": "Warehouse", "timezone": "America/New_York"})

        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "Warehouse"
        assert body["timezone"] == "America/New_York"
        assert body["camera_count"] == 0

    def test_timezone_defaults_to_utc(self, client):
        body = client.post("/locations", json={"name": "Warehouse"}).json()
        assert body["timezone"] == "UTC"

    def test_camera_count_reflects_real_cameras(self, client):
        location_id = client.post("/locations", json={"name": "Warehouse"}).json()["id"]
        _create_camera(client, location_id=location_id, name="cam-1")
        _create_camera(client, location_id=location_id, name="cam-2")

        locations = {loc["name"]: loc for loc in client.get("/locations").json()}

        assert locations["Warehouse"]["camera_count"] == 2
        assert locations["Main location"]["camera_count"] == 0

    def test_two_locations_in_the_same_organization_cannot_share_a_name(self, client):
        client.post("/locations", json={"name": "Warehouse"})

        response = client.post("/locations", json={"name": "Warehouse"})

        assert response.status_code == 409

    def test_the_same_name_is_fine_in_a_different_organization(self, client, register_user):
        client.post("/locations", json={"name": "Warehouse"})
        other = register_user("other@example.com")

        response = other.post("/locations", json={"name": "Warehouse"})

        assert response.status_code == 200

    def test_a_member_can_list_locations_but_not_create_one(self, client, register_user, add_member):
        member = register_user("member@example.com")
        add_member(client, member)

        assert member.get("/locations").status_code == 200
        assert member.post("/locations", json={"name": "Warehouse"}).status_code == 403

    def test_requires_authentication(self, anonymous_client):
        assert anonymous_client.get("/locations").status_code == 401

    def test_an_empty_name_is_rejected(self, client):
        assert client.post("/locations", json={"name": ""}).status_code == 422


class TestUpdate:
    def test_renaming_a_location(self, client):
        location_id = client.post("/locations", json={"name": "Warehouse"}).json()["id"]

        body = client.patch(f"/locations/{location_id}", json={"name": "Main Warehouse"}).json()

        assert body["name"] == "Main Warehouse"

    def test_changing_the_timezone(self, client):
        location_id = client.post("/locations", json={"name": "Warehouse"}).json()["id"]

        body = client.patch(f"/locations/{location_id}", json={"timezone": "Asia/Dhaka"}).json()

        assert body["timezone"] == "Asia/Dhaka"
        assert body["name"] == "Warehouse"  # untouched

    def test_renaming_to_a_name_already_used_in_the_org_is_rejected(self, client):
        client.post("/locations", json={"name": "Warehouse"})
        second_id = client.post("/locations", json={"name": "Office"}).json()["id"]

        response = client.patch(f"/locations/{second_id}", json={"name": "Warehouse"})

        assert response.status_code == 409

    def test_a_member_cannot_update_a_location(self, client, register_user, add_member):
        location_id = client.post("/locations", json={"name": "Warehouse"}).json()["id"]
        member = register_user("member@example.com")
        add_member(client, member)

        response = member.patch(f"/locations/{location_id}", json={"name": "Nope"})

        assert response.status_code == 403

    def test_cannot_update_another_organizations_location(self, client, register_user):
        location_id = client.post("/locations", json={"name": "Warehouse"}).json()["id"]
        other = register_user("other@example.com")

        response = other.patch(f"/locations/{location_id}", json={"name": "Nope"})

        assert response.status_code == 404

    def test_an_unknown_location_is_404(self, client):
        assert client.patch(f"/locations/{uuid.uuid4()}", json={"name": "x"}).status_code == 404


class TestDelete:
    def test_deleting_an_empty_location(self, client):
        location_id = client.post("/locations", json={"name": "Warehouse"}).json()["id"]

        response = client.delete(f"/locations/{location_id}")

        assert response.status_code == 204
        assert location_id not in [loc["id"] for loc in client.get("/locations").json()]

    def test_deleting_a_location_with_cameras_on_it_is_refused(self, client):
        location_id = client.post("/locations", json={"name": "Warehouse"}).json()["id"]
        _create_camera(client, location_id=location_id)

        response = client.delete(f"/locations/{location_id}")

        assert response.status_code == 409
        assert "1 camera" in response.json()["detail"]
        # Nothing was silently lost.
        assert any(loc["id"] == location_id for loc in client.get("/locations").json())

    def test_moving_the_camera_out_then_lets_the_location_be_deleted(self, client):
        location_id = client.post("/locations", json={"name": "Warehouse"}).json()["id"]
        camera_id = _create_camera(client, location_id=location_id)["id"]
        main = next(loc for loc in client.get("/locations").json() if loc["name"] == "Main location")

        client.patch(f"/cameras/{camera_id}", json={"location_id": main["id"]})

        assert client.delete(f"/locations/{location_id}").status_code == 204

    def test_a_member_cannot_delete_a_location(self, client, register_user, add_member):
        location_id = client.post("/locations", json={"name": "Warehouse"}).json()["id"]
        member = register_user("member@example.com")
        add_member(client, member)

        assert member.delete(f"/locations/{location_id}").status_code == 403

    def test_cannot_delete_another_organizations_location(self, client, register_user):
        location_id = client.post("/locations", json={"name": "Warehouse"}).json()["id"]
        other = register_user("other@example.com")

        assert other.delete(f"/locations/{location_id}").status_code == 404

    def test_an_unknown_location_is_404(self, client):
        assert client.delete(f"/locations/{uuid.uuid4()}").status_code == 404
