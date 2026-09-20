"""End-to-end tests: real YOLO inference (yolov8n.pt), real PostgreSQL, no mocks.

Run from any directory: the fixture switches to backend/ because model weights are
resolved relative to the working directory (existing behavior of the detector).
"""
import time
import uuid
from pathlib import Path

import cv2
import pytest
from ultralytics.utils import ASSETS

from app.models import Job

BACKEND_DIR = Path(__file__).resolve().parents[1]
BUS_IMAGE = ASSETS / "bus.jpg"


@pytest.fixture(autouse=True)
def run_from_backend_dir(monkeypatch):
    monkeypatch.chdir(BACKEND_DIR)


def _run_job(client, video_source, timeout=180):
    response = client.post(
        "/jobs", json={"video_source": str(video_source), "model_type": "yolo", "confidence_threshold": 0.25}
    )
    assert response.status_code == 200
    job_id = response.json()["id"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/jobs/{job_id}").json()
        if job["status"] in ("completed", "failed"):
            return job
        time.sleep(0.5)
    pytest.fail(f"job {job_id} did not finish within {timeout}s")


def test_image_job_completes_and_result_is_persisted(client, db_session):
    job = _run_job(client, BUS_IMAGE)

    assert job["status"] == "completed", job["error"]
    assert job["error"] is None
    assert job["result"]["type"] == "image"
    labels = {d["label"] for d in job["result"]["detections"]}
    assert {"bus", "person"} <= labels

    row = db_session.get(Job, uuid.UUID(job["id"]))
    assert row.status == "completed"
    assert row.result == job["result"]


def test_video_job_completes_with_one_entry_per_frame(client, tmp_path):
    image = cv2.imread(str(BUS_IMAGE))
    height, width = image.shape[:2]
    video_path = tmp_path / "bus.avi"
    writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"MJPG"), 5.0, (width, height))
    assert writer.isOpened()
    for _ in range(5):
        writer.write(image)
    writer.release()

    job = _run_job(client, video_path)

    assert job["status"] == "completed", job["error"]
    assert job["result"]["type"] == "video"
    frames = job["result"]["frames"]
    assert [f["frame"] for f in frames] == [0, 1, 2, 3, 4]
    assert any(d["label"] == "bus" for f in frames for d in f["detections"])


def test_missing_image_marks_job_failed_with_error_persisted(client, db_session, tmp_path):
    job = _run_job(client, tmp_path / "does-not-exist.jpg")

    assert job["status"] == "failed"
    assert job["result"] is None
    assert job["error"]

    row = db_session.get(Job, uuid.UUID(job["id"]))
    assert row.status == "failed"
    assert row.error == job["error"]


def test_unopenable_video_marks_job_failed(client, tmp_path):
    job = _run_job(client, tmp_path / "does-not-exist.mp4")

    assert job["status"] == "failed"
    assert "Could not open video" in job["error"]
