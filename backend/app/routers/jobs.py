import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.detection_runner import run_detection_job
from app.models import Job
from app.schemas import JobCreateRequest, JobCreateResponse, JobRead, JobStatus

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobCreateResponse)
def create_job(
    request: JobCreateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    job = Job(
        video_source=request.video_source,
        model_type=request.model_type.value,
        confidence_threshold=request.confidence_threshold,
        status=JobStatus.pending.value,
    )
    db.add(job)
    db.commit()
    background_tasks.add_task(run_detection_job, job.id)
    return JobCreateResponse(id=str(job.id))


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: str, db: Session = Depends(get_db)):
    try:
        parsed_id = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Job not found")
    job = db.get(Job, parsed_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("", response_model=list[JobRead])
def list_jobs(db: Session = Depends(get_db)):
    return db.scalars(select(Job).order_by(Job.created_at)).all()
