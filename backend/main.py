import sys
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

AI_ENGINE_DIR = Path(__file__).resolve().parent.parent / "ai-engine"
sys.path.insert(0, str(AI_ENGINE_DIR))

from detector import Detector  # noqa: E402

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:1420"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ModelType(str, Enum):
    yolo = "yolo"
    yolo_seg = "yolo_seg"
    yolo_pose = "yolo_pose"


MODEL_WEIGHTS = {
    ModelType.yolo: "yolov8n.pt",
    ModelType.yolo_seg: "yolov8n-seg.pt",
    ModelType.yolo_pose: "yolov8n-pose.pt",
}

VIDEO_EXTENSIONS = (".mp4", ".avi", ".mov", ".mkv")


class JobStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class JobCreateRequest(BaseModel):
    video_source: str
    model_type: ModelType
    confidence_threshold: float = Field(default=0.25, ge=0.0, le=1.0)


class JobCreateResponse(BaseModel):
    id: str


class Job(BaseModel):
    id: str
    video_source: str
    model_type: ModelType
    confidence_threshold: float
    status: JobStatus
    created_at: datetime
    result: Optional[dict] = None
    error: Optional[str] = None


jobs: dict[str, Job] = {}


def run_detection_job(job_id: str) -> None:
    job = jobs[job_id]
    job.status = JobStatus.running

    try:
        weights = MODEL_WEIGHTS[job.model_type]
        detector = Detector(model_path=weights)
        is_video = job.video_source.lower().endswith(VIDEO_EXTENSIONS)

        if is_video:
            frames = [
                {"frame": i, "detections": [asdict(d) for d in dets]}
                for i, dets in enumerate(
                    detector.detect_video(job.video_source, conf=job.confidence_threshold)
                )
            ]
            job.result = {"type": "video", "frames": frames}
        else:
            detections = detector.detect_image(job.video_source, conf=job.confidence_threshold)
            job.result = {"type": "image", "detections": [asdict(d) for d in detections]}

        job.status = JobStatus.completed
    except Exception as exc:
        job.status = JobStatus.failed
        job.error = str(exc)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/jobs", response_model=JobCreateResponse)
def create_job(request: JobCreateRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    jobs[job_id] = Job(
        id=job_id,
        video_source=request.video_source,
        model_type=request.model_type,
        confidence_threshold=request.confidence_threshold,
        status=JobStatus.pending,
        created_at=datetime.now(timezone.utc),
    )
    background_tasks.add_task(run_detection_job, job_id)
    return JobCreateResponse(id=job_id)


@app.get("/jobs/{job_id}", response_model=Job)
def get_job(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/jobs", response_model=list[Job])
def list_jobs():
    return list(jobs.values())
