import sys
import uuid
from dataclasses import asdict
from pathlib import Path

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Job
from app.schemas import JobStatus, ModelType

AI_ENGINE_DIR = Path(__file__).resolve().parents[2] / "ai-engine"
sys.path.insert(0, str(AI_ENGINE_DIR))

from detector import Detector  # noqa: E402

MODEL_WEIGHTS = {
    ModelType.yolo: "yolov8n.pt",
    ModelType.yolo_seg: "yolov8n-seg.pt",
    ModelType.yolo_pose: "yolov8n-pose.pt",
}

VIDEO_EXTENSIONS = (".mp4", ".avi", ".mov", ".mkv")


def _detect(video_source: str, model_type: ModelType, confidence_threshold: float) -> dict:
    detector = Detector(model_path=MODEL_WEIGHTS[model_type])

    if video_source.lower().endswith(VIDEO_EXTENSIONS):
        frames = [
            {"frame": i, "detections": [asdict(d) for d in dets]}
            for i, dets in enumerate(detector.detect_video(video_source, conf=confidence_threshold))
        ]
        return {"type": "video", "frames": frames}

    detections = detector.detect_image(video_source, conf=confidence_threshold)
    return {"type": "image", "detections": [asdict(d) for d in detections]}


def run_detection_job(job_id: uuid.UUID) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        job.status = JobStatus.running.value
        db.commit()

        try:
            result = _detect(job.video_source, ModelType(job.model_type), job.confidence_threshold)
        except Exception as exc:
            job.status = JobStatus.failed.value
            job.error = str(exc)
        else:
            job.status = JobStatus.completed.value
            job.result = result
        db.commit()


def reconcile_interrupted_jobs() -> int:
    """Mark jobs left pending/running by a previous process as failed.

    Assumes a single backend process: a second live worker's in-flight jobs would be
    wrongly failed by this.
    """
    with SessionLocal() as db:
        stale = db.scalars(
            select(Job).where(Job.status.in_([JobStatus.pending.value, JobStatus.running.value]))
        ).all()
        for job in stale:
            job.status = JobStatus.failed.value
            job.error = "Interrupted by backend restart"
        db.commit()
        return len(stale)
