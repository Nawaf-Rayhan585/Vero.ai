from fastapi.testclient import TestClient

from app.detection_runner import reconcile_interrupted_jobs
from app.models import Job


def _add_jobs(db_session, *statuses):
    jobs = [
        Job(video_source=f"{i}.jpg", model_type="yolo", confidence_threshold=0.25, status=status)
        for i, status in enumerate(statuses)
    ]
    db_session.add_all(jobs)
    db_session.commit()
    return [job.id for job in jobs]


def _statuses(db_session, ids):
    db_session.expire_all()
    return [(job.status, job.error) for job in (db_session.get(Job, i) for i in ids)]


def test_reconcile_fails_only_pending_and_running_jobs(db_session):
    ids = _add_jobs(db_session, "pending", "running", "completed", "failed")

    assert reconcile_interrupted_jobs() == 2

    assert _statuses(db_session, ids) == [
        ("failed", "Interrupted by backend restart"),
        ("failed", "Interrupted by backend restart"),
        ("completed", None),
        ("failed", None),
    ]


def test_reconcile_with_nothing_to_do_returns_zero(db_session):
    _add_jobs(db_session, "completed")
    assert reconcile_interrupted_jobs() == 0


def test_backend_startup_reconciles_interrupted_jobs(db_session):
    from main import app

    (job_id,) = _add_jobs(db_session, "running")

    with TestClient(app):
        pass

    assert _statuses(db_session, [job_id]) == [("failed", "Interrupted by backend restart")]
