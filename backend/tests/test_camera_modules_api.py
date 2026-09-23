"""Per-camera AI module selection: the module->detector-class mapping, the
`enabled_modules` field on the camera API, and the guard on starting tracking."""
import uuid

import pytest
from sqlalchemy import text

from app.modules import ALL_MODULES, DEFAULT_MODULES, detector_class_ids


class TestDetectorClassIds:
    def test_people_only_is_the_default_and_detects_person(self):
        assert DEFAULT_MODULES == ("people",)
        assert detector_class_ids(DEFAULT_MODULES) == [0]

    def test_vehicles_map_to_car_motorcycle_bus_truck(self):
        assert detector_class_ids(["vehicles"]) == [2, 3, 5, 7]

    def test_people_and_vehicles_together(self):
        assert detector_class_ids(["people", "vehicles"]) == [0, 2, 3, 5, 7]

    def test_order_of_the_selection_does_not_matter(self):
        assert detector_class_ids(["vehicles", "people"]) == [0, 2, 3, 5, 7]

    @pytest.mark.parametrize("module", ["ocr", "qr", "barcode"])
    def test_reading_modules_need_no_detector(self, module):
        assert detector_class_ids([module]) == []

    def test_no_modules_needs_no_detector(self):
        assert detector_class_ids([]) == []

    def test_the_five_modules_are_exactly_these(self):
        assert set(ALL_MODULES) == {"people", "vehicles", "ocr", "qr", "barcode"}


def _create_camera(client, **overrides) -> dict:
    body = {"name": "Front door", "rtsp_url": "rtsp://192.0.2.10:554/stream1"}
    body.update(overrides)
    response = client.post("/cameras", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_a_new_camera_defaults_to_people_only(client):
    assert _create_camera(client)["enabled_modules"] == ["people"]


def test_a_camera_can_be_created_with_a_module_selection(client):
    camera = _create_camera(client, enabled_modules=["vehicles", "qr"])

    assert camera["enabled_modules"] == ["vehicles", "qr"]
    assert client.get(f"/cameras/{camera['id']}").json()["enabled_modules"] == ["vehicles", "qr"]


def test_the_selection_can_be_changed_and_persists(client):
    camera_id = _create_camera(client)["id"]

    response = client.patch(f"/cameras/{camera_id}", json={"enabled_modules": ["people", "vehicles", "ocr"]})

    assert response.status_code == 200
    assert response.json()["enabled_modules"] == ["people", "vehicles", "ocr"]
    assert client.get(f"/cameras/{camera_id}").json()["enabled_modules"] == ["people", "vehicles", "ocr"]


def test_changing_the_selection_leaves_the_other_camera_fields_alone(client):
    camera_id = _create_camera(client, notes="north side")["id"]

    body = client.patch(f"/cameras/{camera_id}", json={"enabled_modules": ["barcode"]}).json()

    assert body["name"] == "Front door"
    assert body["location_name"] == "Main location"
    assert body["notes"] == "north side"


def test_updating_other_fields_leaves_the_selection_alone(client):
    camera_id = _create_camera(client, enabled_modules=["qr", "barcode"])["id"]

    body = client.patch(f"/cameras/{camera_id}", json={"name": "Renamed"}).json()

    assert body["name"] == "Renamed"
    assert body["enabled_modules"] == ["qr", "barcode"]


def test_an_explicit_null_selection_means_leave_it_unchanged(client):
    camera_id = _create_camera(client, enabled_modules=["ocr"])["id"]

    response = client.patch(f"/cameras/{camera_id}", json={"enabled_modules": None})

    assert response.status_code == 200
    assert response.json()["enabled_modules"] == ["ocr"]


def test_repeated_modules_collapse_to_one_keeping_first_seen_order(client):
    camera = _create_camera(client, enabled_modules=["qr", "people", "qr", "people"])

    assert camera["enabled_modules"] == ["qr", "people"]


def test_an_empty_selection_is_allowed_but_stored_as_empty(client):
    camera_id = _create_camera(client)["id"]

    body = client.patch(f"/cameras/{camera_id}", json={"enabled_modules": []}).json()

    assert body["enabled_modules"] == []


@pytest.mark.parametrize("bad", [["license_plates"], ["people", "nope"], "people", [1], {"people": True}])
def test_unknown_or_malformed_modules_return_422(client, bad):
    camera_id = _create_camera(client)["id"]

    assert client.patch(f"/cameras/{camera_id}", json={"enabled_modules": bad}).status_code == 422
    assert client.post("/cameras", json={"name": "x", "rtsp_url": "rtsp://x/y", "enabled_modules": bad}).status_code == 422


def test_a_camera_that_predates_module_selection_reads_as_people_only(anonymous_client, db_session):
    # A row inserted the way it would have been before the enabled_modules column (or
    # organizations at all) existed — no enabled_modules, no location — must pick up the
    # server default and get adopted into the first organization to register (Phase 10's
    # adopt_orphans), so upgraded installs keep working exactly as they did.
    camera_id = uuid.uuid4()
    db_session.execute(
        text("INSERT INTO cameras (id, name, rtsp_url, connection_status) VALUES (:id, 'Old camera', 'rtsp://x/y', 'unknown')"),
        {"id": camera_id},
    )
    db_session.commit()

    response = anonymous_client.post(
        "/auth/register",
        json={"email": "owner@example.com", "password": "test-password-123", "name": "Owner", "organization_name": "Org"},
    )
    anonymous_client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"

    body = anonymous_client.get(f"/cameras/{camera_id}").json()
    assert body["enabled_modules"] == ["people"]
    assert body["location_name"] == "Main location"


def test_starting_tracking_with_no_modules_enabled_returns_422(client):
    camera_id = _create_camera(client, enabled_modules=[])["id"]

    response = client.post(f"/cameras/{camera_id}/tracking/start")

    assert response.status_code == 422
    assert "at least one AI module" in response.json()["detail"]
    assert client.get(f"/cameras/{camera_id}/tracking/status").json()["status"] == "stopped"
