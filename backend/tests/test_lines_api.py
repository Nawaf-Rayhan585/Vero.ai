import uuid

import pytest

LINE_KEYS = {"id", "camera_id", "name", "x1", "y1", "x2", "y2", "created_at"}


def _create_camera(client, **overrides) -> dict:
    body = {"name": "Front door", "rtsp_url": "rtsp://192.0.2.10:554/stream1"}
    body.update(overrides)
    return client.post("/cameras", json=body).json()


def _create_line(client, camera_id, **overrides) -> dict:
    body = {"name": "Entrance", "x1": 0.1, "y1": 0.5, "x2": 0.9, "y2": 0.5}
    body.update(overrides)
    return client.post(f"/cameras/{camera_id}/lines", json=body).json()


def test_create_line_returns_full_shape(client):
    camera_id = _create_camera(client)["id"]

    response = client.post(f"/cameras/{camera_id}/lines", json={"name": "Entrance", "x1": 0.1, "y1": 0.5, "x2": 0.9, "y2": 0.5})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == LINE_KEYS
    assert body["camera_id"] == camera_id
    assert body["name"] == "Entrance"
    assert (body["x1"], body["y1"], body["x2"], body["y2"]) == (0.1, 0.5, 0.9, 0.5)


def test_create_line_for_unknown_camera_returns_404(client):
    response = client.post(f"/cameras/{uuid.uuid4()}/lines", json={"name": "x", "x1": 0, "y1": 0, "x2": 1, "y2": 1})
    assert response.status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"name": "", "x1": 0, "y1": 0, "x2": 1, "y2": 1},  # empty name
        {"name": "x", "x1": -0.1, "y1": 0, "x2": 1, "y2": 1},  # out of [0,1]
        {"name": "x", "x1": 0, "y1": 0, "x2": 1.5, "y2": 1},  # out of [0,1]
        {"name": "x", "y1": 0, "x2": 1, "y2": 1},  # missing x1
    ],
)
def test_invalid_create_requests_return_422(client, body):
    camera_id = _create_camera(client)["id"]
    assert client.post(f"/cameras/{camera_id}/lines", json=body).status_code == 422


def test_list_lines_for_a_camera_in_creation_order(client):
    camera_id = _create_camera(client)["id"]
    names = [_create_line(client, camera_id, name=f"line-{i}")["name"] for i in range(3)]

    listed = client.get(f"/cameras/{camera_id}/lines").json()

    assert [line["name"] for line in listed] == names


def test_list_lines_only_returns_this_cameras_lines(client):
    camera_a = _create_camera(client, name="A")["id"]
    camera_b = _create_camera(client, name="B")["id"]
    _create_line(client, camera_a, name="a-line")
    _create_line(client, camera_b, name="b-line")

    assert [line["name"] for line in client.get(f"/cameras/{camera_a}/lines").json()] == ["a-line"]
    assert [line["name"] for line in client.get(f"/cameras/{camera_b}/lines").json()] == ["b-line"]


def test_list_lines_for_unknown_camera_returns_404(client):
    assert client.get(f"/cameras/{uuid.uuid4()}/lines").status_code == 404


def test_delete_line(client):
    camera_id = _create_camera(client)["id"]
    line_id = _create_line(client, camera_id)["id"]

    response = client.delete(f"/lines/{line_id}")

    assert response.status_code == 204
    assert client.get(f"/cameras/{camera_id}/lines").json() == []


def test_delete_unknown_line_returns_404(client):
    assert client.delete(f"/lines/{uuid.uuid4()}").status_code == 404


def test_deleting_a_camera_cascades_to_delete_its_lines(client, db_session):
    from app.models import Line

    camera_id = _create_camera(client)["id"]
    line_id = _create_line(client, camera_id)["id"]

    assert client.delete(f"/cameras/{camera_id}").status_code == 204

    db_session.expire_all()
    assert db_session.get(Line, uuid.UUID(line_id)) is None
