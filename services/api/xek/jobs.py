import threading
from datetime import UTC, datetime

from celery import Celery
from sqlalchemy import select, update

from .config import settings
from .db import Job, Session

celery = Celery("xek", broker=settings().redis_url, backend=settings().redis_url)
celery.conf.update(task_track_started=True, worker_prefetch_multiplier=1,
                   task_acks_late=True, task_reject_on_worker_lost=True,
                   beat_schedule={"scheduled-production": {"task": "xek.tick", "schedule": 15.0}})

ACTIVE = {"queued", "running", "retrying", "paused"}


def dispatch(job_id: str):
    if settings().worker_mode == "inline":
        threading.Thread(target=execute, args=(job_id,), daemon=True).start()
    else:
        execute_task.delay(job_id)


def update_job(job_id: str, stage: str, progress: int):
    with Session.begin() as db:
        job = db.get(Job, job_id)
        if job.cancel_requested:
            raise InterruptedError("Cancelled by owner")
        if job.state == "paused" or job.payload.get("pause_requested"):
            raise InterruptedError("Paused by owner; resume restarts from completed checkpoints")
        job.stage, job.progress = stage, progress
        job.logs = [*job.logs, {"at": datetime.now(UTC).isoformat(), "stage": stage}][-500:]


def cancelled(job_id: str):
    with Session() as db:
        job = db.get(Job, job_id)
        return job.cancel_requested or job.state == "paused" or job.payload.get("pause_requested", False)


def execute(job_id: str):
    # Compare-and-set prevents duplicate broker delivery from executing the same job twice.
    with Session.begin() as db:
        claimed = db.execute(update(Job).where(Job.id == job_id, Job.state.in_(["queued", "retrying"]))
                             .values(state="running", attempts=Job.attempts + 1))
        if claimed.rowcount != 1:
            return
        kind = db.get(Job, job_id).kind
    try:
        from .pipeline import production, screenplay_job, shorts_job
        from .publishing import upload_job
        handlers = {"screenplay": screenplay_job, "production": production,
                    "shorts": shorts_job, "publish": upload_job}
        handlers[kind](job_id)
        with Session.begin() as db:
            job = db.get(Job, job_id)
            if job.cancel_requested:
                job.state = "cancelled"
            elif job.payload.get("pause_requested"):
                job.state = "paused"
            else:
                job.state, job.progress, job.stage = "completed", 100, "completed"
    except InterruptedError:
        with Session.begin() as db:
            job = db.get(Job, job_id)
            job.state = "paused" if job.payload.get("pause_requested") else "cancelled"
    except Exception as exc:
        with Session.begin() as db:
            job = db.get(Job, job_id)
            if job.cancel_requested or job.payload.get("pause_requested"):
                job.state = "paused" if job.payload.get("pause_requested") else "cancelled"
                return
            job.state, job.error = "failed", str(exc)[:4000]
            job.logs = [*job.logs, {"at": datetime.now(UTC).isoformat(), "stage": "failed",
                                    "error": str(exc)[:1000]}]


@celery.task(name="xek.execute")
def execute_task(job_id: str):
    execute(job_id)


@celery.task(name="xek.tick")
def tick():
    with Session.begin() as db:
        due = db.scalars(select(Job).where(Job.state == "scheduled", Job.run_at <= datetime.now(UTC))).all()
        ids = [job.id for job in due]
        for job in due:
            job.state = "queued"
    for job_id in ids:
        try:
            dispatch(job_id)
        except Exception:
            with Session.begin() as db:
                db.get(Job, job_id).state = "scheduled"
