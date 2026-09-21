import uuid

import pytest

from app.crypto import decrypt_password
from app.models import Camera

CAMERA_KEYS = {
    "id",
    "name",
    "rtsp_url",
    "username",
    "has_password",
    "location_label",
    "notes",
    "created_at",
    "updated_at",
    "connection_status",
    "last_tested_at",
    "last_error",
    "last_fps",
    "last_width",
    "last_height",
    "enabled_modules",
}


def _create(client, **overrides):
    body = {"name": "Front door", "rtsp_url": "rtsp://192.0.2.10:554/stream1"}
    body.update(overrides)
    return client.post("/cameras", json=body)


def test_create_camera_returns_full_shape_with_no_password_field(client):
    response = _create(client, username="admin", password="hunter2")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == CAMERA_KEYS
    assert "password" not in body
    assert "encrypted_password" not in body
    assert body["has_password"] is True
    assert body["username"] == "admin"
    assert body["connection_status"] == "unknown"
    assert body["last_tested_at"] is None


def test_create_camera_without_password_reports_has_password_false(client):
    body = _create(client).json()
    assert body["has_password"] is False


def test_created_password_is_encrypted_at_rest_and_recoverable(client, db_session):
    camera_id = _create(client, password="hunter2").json()["id"]

    row = db_session.get(Camera, uuid.UUID(camera_id))
    assert row.encrypted_password is not None
    assert row.encrypted_password != "hunter2"
    assert decrypt_password(row.encrypted_password) == "hunter2"


def test_get_camera(client):
    camera_id = _create(client).json()["id"]
    body = client.get(f"/cameras/{camera_id}").json()
    assert body["id"] == camera_id
    assert body["name"] == "Front door"


def test_list_cameras_in_creation_order(client):
    ids = [_create(client, name=f"cam-{i}").json()["id"] for i in range(3)]
    listed = client.get("/cameras").json()
    assert [c["id"] for c in listed] == ids


def test_list_cameras_empty(client):
    assert client.get("/cameras").json() == []


@pytest.mark.parametrize("camera_id", [str(uuid.uuid4()), "not-a-uuid"])
def test_get_unknown_camera_returns_404(client, camera_id):
    response = client.get(f"/cameras/{camera_id}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Camera not found"}


@pytest.mark.parametrize(
    "body",
    [
        {"rtsp_url": "rtsp://x/y"},  # missing name
        {"name": "cam"},  # missing rtsp_url
        {"name": "", "rtsp_url": "rtsp://x/y"},  # empty name
        {"name": "cam", "rtsp_url": ""},  # empty rtsp_url
    ],
)
def test_invalid_create_requests_return_422(client, body):
    assert client.post("/cameras", json=body).status_code == 422


def test_update_camera_name_and_location(client):
    camera_id = _create(client).json()["id"]

    body = client.patch(f"/cameras/{camera_id}", json={"name": "Back door", "location_label": "Warehouse"}).json()

    assert body["name"] == "Back door"
    assert body["location_label"] == "Warehouse"
    assert body["rtsp_url"] == "rtsp://192.0.2.10:554/stream1"  # untouched


def test_update_omitting_password_leaves_existing_password_unchanged(client, db_session):
    camera_id = _create(client, password="original").json()["id"]

    client.patch(f"/cameras/{camera_id}", json={"name": "renamed"})

    row = db_session.get(Camera, uuid.UUID(camera_id))
    assert decrypt_password(row.encrypted_password) == "original"


def test_update_with_new_password_replaces_it(client, db_session):
    camera_id = _create(client, password="original").json()["id"]

    client.patch(f"/cameras/{camera_id}", json={"password": "replaced"})

    row = db_session.get(Camera, uuid.UUID(camera_id))
    assert decrypt_password(row.encrypted_password) == "replaced"


def test_update_with_empty_string_password_clears_it(client):
    camera_id = _create(client, password="original").json()["id"]

    body = client.patch(f"/cameras/{camera_id}", json={"password": ""}).json()

    assert body["has_password"] is False


def test_update_unknown_camera_returns_404(client):
    response = client.patch(f"/cameras/{uuid.uuid4()}", json={"name": "x"})
    assert response.status_code == 404


def test_delete_camera(client):
    camera_id = _create(client).json()["id"]

    response = client.delete(f"/cameras/{camera_id}")
    assert response.status_code == 204
    assert client.get(f"/cameras/{camera_id}").status_code == 404


def test_delete_unknown_camera_returns_404(client):
    assert client.delete(f"/cameras/{uuid.uuid4()}").status_code == 404
