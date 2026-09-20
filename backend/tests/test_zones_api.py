import uuid

import pytest

ZONE_KEYS = {"id", "camera_id", "name", "points", "created_at"}
SQUARE = [{"x": 0.2, "y": 0.2}, {"x": 0.8, "y": 0.2}, {"x": 0.8, "y": 0.8}, {"x": 0.2, "y": 0.8}]


def _create_camera(client, **overrides) -> dict:
    body = {"name": "Front door", "rtsp_url": "rtsp://192.0.2.10:554/stream1"}
    body.update(overrides)
    return client.post("/cameras", json=body).json()


def _create_zone(client, camera_id, **overrides) -> dict:
    body = {"name": "Checkout", "points": SQUARE}
    body.update(overrides)
    return client.post(f"/cameras/{camera_id}/zones", json=body).json()


def test_create_zone_returns_full_shape(client):
    camera_id = _create_camera(client)["id"]

    response = client.post(f"/cameras/{camera_id}/zones", json={"name": "Checkout", "points": SQUARE})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == ZONE_KEYS
    assert body["camera_id"] == camera_id
    assert body["name"] == "Checkout"
    assert body["points"] == SQUARE


def test_a_zone_can_have_more_than_four_points(client):
    camera_id = _create_camera(client)["id"]
    hexagon = [{"x": 0.5, "y": 0.1}, {"x": 0.9, "y": 0.3}, {"x": 0.9, "y": 0.7}, {"x": 0.5, "y": 0.9}, {"x": 0.1, "y": 0.7}, {"x": 0.1, "y": 0.3}]

    body = _create_zone(client, camera_id, points=hexagon)

    assert body["points"] == hexagon


def test_create_zone_for_unknown_camera_returns_404(client):
    response = client.post(f"/cameras/{uuid.uuid4()}/zones", json={"name": "x", "points": SQUARE})
    assert response.status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"name": "", "points": SQUARE},  # empty name
        {"name": "x", "points": SQUARE[:2]},  # a polygon needs at least 3 points
        {"name": "x", "points": []},
        {"name": "x"},  # missing points
        {"name": "x", "points": [{"x": 0.1, "y": 0.1}, {"x": 0.5, "y": 0.1}, {"x": 1.5, "y": 0.9}]},  # x out of [0,1]
        {"name": "x", "points": [{"x": 0.1, "y": 0.1}, {"x": 0.5, "y": 0.1}, {"x": 0.5, "y": -0.2}]},  # y out of [0,1]
        {"name": "x", "points": [{"x": 0.1, "y": 0.1}, {"x": 0.5, "y": 0.1}, {"x": 0.5}]},  # point missing y
        {"name": "x", "points": [{"x": 0.5, "y": 0.5}] * 101},  # more than the 100-point cap
    ],
)
def test_invalid_create_requests_return_422(client, body):
    camera_id = _create_camera(client)["id"]
    assert client.post(f"/cameras/{camera_id}/zones", json=body).status_code == 422


def test_list_zones_for_a_camera_in_creation_order(client):
    camera_id = _create_camera(client)["id"]
    names = [_create_zone(client, camera_id, name=f"zone-{i}")["name"] for i in range(3)]

    listed = client.get(f"/cameras/{camera_id}/zones").json()

    assert [zone["name"] for zone in listed] == names


def test_list_zones_only_returns_this_cameras_zones(client):
    camera_a = _create_camera(client, name="A")["id"]
    camera_b = _create_camera(client, name="B")["id"]
    _create_zone(client, camera_a, name="a-zone")
    _create_zone(client, camera_b, name="b-zone")

    assert [zone["name"] for zone in client.get(f"/cameras/{camera_a}/zones").json()] == ["a-zone"]
    assert [zone["name"] for zone in client.get(f"/cameras/{camera_b}/zones").json()] == ["b-zone"]


def test_list_zones_for_unknown_camera_returns_404(client):
    assert client.get(f"/cameras/{uuid.uuid4()}/zones").status_code == 404


def test_delete_zone(client):
    camera_id = _create_camera(client)["id"]
    zone_id = _create_zone(client, camera_id)["id"]

    response = client.delete(f"/zones/{zone_id}")

    assert response.status_code == 204
    assert client.get(f"/cameras/{camera_id}/zones").json() == []


def test_delete_unknown_zone_returns_404(client):
    assert client.delete(f"/zones/{uuid.uuid4()}").status_code == 404


def test_delete_zone_with_a_malformed_id_returns_404(client):
    assert client.delete("/zones/not-a-uuid").status_code == 404


def test_deleting_a_camera_cascades_to_delete_its_zones(client, db_session):
    from app.models import Zone

    camera_id = _create_camera(client)["id"]
    zone_id = _create_zone(client, camera_id)["id"]

    assert client.delete(f"/cameras/{camera_id}").status_code == 204

    db_session.expire_all()
    assert db_session.get(Zone, uuid.UUID(zone_id)) is None
