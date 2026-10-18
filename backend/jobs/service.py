"""Postgres-backed job records run on an in-process worker pool.

A job is created `queued`, picked up by a worker thread, and ends `completed`, `failed` or
`cancelled`. Anything still queued or running when the API starts was interrupted by a restart and
is marked failed. Cancelling a queued job is immediate; a running job is asked to stop and does so
at its next `ctx.check_cancelled()`, so an LLM call already in flight finishes first.
"""
from __future__ import annotations

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from backend.config import settings
from backend.db import SessionLocal
from backend.models import Job

logger = logging.getLogger(__name__)

QUEUED, RUNNING, COMPLETED, FAILED, CANCELLED = "queued", "running", "completed", "failed", "cancelled"
TERMINAL_STATES = {COMPLETED, FAILED, CANCELLED}


class JobCancelled(Exception):
    pass


class JobContext:
    def __init__(self, job_id: str):
        self.job_id = job_id

    def progress(self, message: str) -> None:
        with SessionLocal() as db:
            job = db.get(Job, self.job_id)
            if job is not None:
                job.progress = message[:255]
                db.commit()

    def check_cancelled(self) -> None:
        with SessionLocal() as db:
            job = db.get(Job, self.job_id)
            if job is not None and job.cancel_requested:
                raise JobCancelled()


Handler = Callable[[JobContext, dict[str, Any]], "dict[str, Any] | None"]
_HANDLERS: dict[str, Handler] = {}
_executor: ThreadPoolExecutor | None = None


def handler(kind: str) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        _HANDLERS[kind] = fn
        return fn

    return register


def _pool() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=settings.job_workers, thread_name_prefix="job")
    return _executor


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def submit_job(
    db: Session,
    kind: str,
    params: dict[str, Any],
    *,
    user_id: int | None = None,
    group_member_id: int | None = None,
    group_id: int | None = None,
    meeting_id: int | None = None,
) -> Job:
    import backend.jobs.handlers  # noqa: F401  registers the handlers

    if kind not in _HANDLERS:
        raise ValueError(f"Unknown job kind {kind!r}")
    job = Job(
        id=str(uuid.uuid4()), kind=kind, state=QUEUED, params=params, user_id=user_id,
        group_member_id=group_member_id, group_id=group_id, meeting_id=meeting_id,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    _pool().submit(_run, job.id)
    return job


def _run(job_id: str) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None or job.state != QUEUED:
            return
        job.state, job.started_at = RUNNING, _now()
        db.commit()
        kind, params = job.kind, dict(job.params or {})

    state, result, error, error_type = COMPLETED, None, None, None
    try:
        result = _HANDLERS[kind](JobContext(job_id), params)
    except JobCancelled:
        state = CANCELLED
    except Exception as exc:  # noqa: BLE001 - recorded on the job
        logger.exception("Job %s (%s) failed", job_id, kind)
        state, error, error_type = FAILED, str(exc) or exc.__class__.__name__, exc.__class__.__name__

    with SessionLocal() as db:
        job = db.get(Job, job_id)
        job.state, job.result, job.error, job.error_type, job.finished_at = state, result, error, error_type, _now()
        db.commit()


def request_cancel(db: Session, job: Job) -> Job:
    """Queued jobs are cancelled at once; running jobs are flagged and stop at their next checkpoint."""
    if job.state == QUEUED:
        job.state, job.finished_at, job.cancel_requested = CANCELLED, _now(), True
    elif job.state == RUNNING:
        job.cancel_requested = True
    db.commit()
    db.refresh(job)
    return job


def recover_interrupted() -> int:
    with SessionLocal() as db:
        stale = db.query(Job).filter(Job.state.in_([QUEUED, RUNNING])).all()
        for job in stale:
            job.state, job.error, job.finished_at = FAILED, "Interrupted by a restart", _now()
        db.commit()
        return len(stale)
