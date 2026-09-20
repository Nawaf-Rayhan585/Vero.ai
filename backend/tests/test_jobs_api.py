"""API-layer tests for /jobs. The detection task is stubbed out here so these stay fast;
real inference is covered by test_detection_pipeline.py."""
import uuid

import pytest

from app.models import Job

JOB_KEYS = {
    "id",
    "video_source",
    "model_type",
    "confidence_threshold",
    "status",
    "created_at",
    "result",
    "error",
}


@pytest.fixture(autouse=True)
def stub_detection(monkeypatch):
    monkeypatch.setattr("app.routers.jobs.run_detection_job", lambda job_id: None)


def _create(client, **overrides):
    body = {"video_source": "C:/media/a.jpg", "model_type": "yolo", "confidence_threshold": 0.4}
    body.update(overrides)
    return client.post("/jobs", json=body)


def test_create_job_returns_id_and_persists_pending_row(client, db_session):
    response = _create(client)
    assert response.status_code == 200
    job_id = response.json()["id"]
    uuid.UUID(job_id)

    row = db_session.get(Job, uuid.UUID(job_id))
    assert row is not None
    assert row.status == "pending"
    assert row.video_source == "C:/media/a.jpg"
    assert row.model_type == "yolo"
    assert row.confidence_threshold == 0.4


def test_get_job_json_shape_is_unchanged_from_prototype(client):
    job_id = _create(client).json()["id"]
    body = client.get(f"/jobs/{job_id}").json()
    assert set(body) == JOB_KEYS
    assert body["id"] == job_id
    assert body["status"] == "pending"
    assert body["result"] is None
    assert body["error"] is None
    assert body["created_at"]


def test_default_confidence_threshold(client):
    job_id = client.post("/jobs", json={"video_source": "x.jpg", "model_type": "yolo_seg"}).json()["id"]
    assert client.get(f"/jobs/{job_id}").json()["confidence_threshold"] == 0.25


def test_list_jobs_returns_jobs_in_creation_order(client):
    ids = [_create(client, video_source=f"{i}.jpg").json()["id"] for i in range(3)]
    listed = client.get("/jobs").json()
    assert [job["id"] for job in listed] == ids
    assert all(set(job) == JOB_KEYS for job in listed)


def test_list_jobs_empty(client):
    assert client.get("/jobs").json() == []


@pytest.mark.parametrize("job_id", [str(uuid.uuid4()), "not-a-uuid"])
def test_get_unknown_job_returns_404(client, job_id):
    response = client.get(f"/jobs/{job_id}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Job not found"}


@pytest.mark.parametrize(
    "body",
    [
        {"video_source": "x.jpg", "model_type": "not-a-model"},
        {"video_source": "x.jpg", "model_type": "yolo", "confidence_threshold": 1.5},
        {"video_source": "x.jpg", "model_type": "yolo", "confidence_threshold": -0.1},
        {"model_type": "yolo"},
    ],
)
def test_invalid_create_requests_return_422(client, body):
    assert client.post("/jobs", json=body).status_code == 422
