"""Drains QUEUED jobs and dispatches them to the appropriate operation handler.

Explicit dispatch (spec S17 style), mirroring pipeline.py's dispatch for the synchronous
operations. submit_transcript and assess_query are the only operations that ever create a job
(see commands/validator.py and handlers/base.py - status/results/cancel/help never do), so the
else branch below is unreachable in practice; it's kept as a defensive log rather than silently
doing nothing.
"""
from __future__ import annotations

import logging
import threading

from app.admin.notifier import AdminNotifier
from app.diarisation.client import DiarisationClient
from app.github_raginator.client import GithubRaginatorClient
from app.handlers import add_comment, assess_query, submit_transcript
from app.jobs.models import Job
from app.jobs.store import JobStore, Outbox
from app.llm.ollama_client import OllamaClient
from app.settings import StorageSettings

logger = logging.getLogger(__name__)


class JobWorker:
    def __init__(
        self,
        job_store: JobStore,
        diarisation_client: DiarisationClient,
        outbox: Outbox,
        admin_notifier: AdminNotifier,
        storage: StorageSettings,
        github_raginator_client: GithubRaginatorClient,
        ollama_client: OllamaClient,
    ):
        self._job_store = job_store
        self._diarisation_client = diarisation_client
        self._outbox = outbox
        self._admin_notifier = admin_notifier
        self._storage = storage
        self._github_raginator_client = github_raginator_client
        self._ollama_client = ollama_client

    def run_once(self) -> int:
        jobs = self._job_store.list_queued()
        for job in jobs:
            self._process_job(job)
        return len(jobs)

    def _process_job(self, job: Job) -> None:
        try:
            if job.operation == "submit_transcript":
                submit_transcript.execute(
                    job,
                    self._diarisation_client,
                    self._job_store,
                    self._outbox,
                    self._admin_notifier,
                    self._storage,
                )
            elif job.operation == "assess_query":
                assess_query.execute(
                    job,
                    self._diarisation_client,
                    self._github_raginator_client,
                    self._ollama_client,
                    self._job_store,
                    self._outbox,
                    self._admin_notifier,
                )
            elif job.operation == "add_comment":
                add_comment.execute(
                    job,
                    self._diarisation_client,
                    self._job_store,
                    self._outbox,
                    self._admin_notifier,
                )
            else:
                logger.error("Job %s has unsupported queued operation %r", job.job_id, job.operation)
        except Exception:
            # Both handlers' execute() already catch their own expected error types; this is a
            # last-resort guard so one bad job can never take down the worker loop for every
            # other queued job.
            logger.exception("Unhandled error processing job %s", job.job_id)

    def run_forever(self, poll_interval_seconds: float, stop_event: threading.Event) -> None:
        while not stop_event.is_set():
            try:
                self.run_once()
            except Exception:
                logger.exception("Error in job worker loop")
            stop_event.wait(poll_interval_seconds)
