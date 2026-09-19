import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.admin.notifier import AdminNotifier
from app.diarisation.client import GroupSummary
from app.jobs.models import JobState
from app.jobs.store import JobStore, Outbox
from app.jobs.worker import JobWorker
from app.settings import StorageSettings

from tests.fakes import FakeDiarisationClient, FakeGithubRaginatorClient, StubLLM


def _storage(tmp_path: Path) -> StorageSettings:
    s = StorageSettings(
        incoming=tmp_path / "incoming",
        processing=tmp_path / "processing",
        completed=tmp_path / "completed",
        failed=tmp_path / "failed",
        db_path=tmp_path / "unused.db",
    )
    s.incoming.mkdir(parents=True, exist_ok=True)
    return s


def _queued_job(job_store: JobStore, storage: StorageSettings, sender="alice@uni.ac.uk", speakers=None):
    stored_path = storage.incoming / f"{uuid.uuid4().hex}_meeting.vtt"
    stored_path.write_text("WEBVTT\n\n1\n00:00:01.000 --> 00:00:02.000\nAlice: hi\n")
    job = job_store.create_job(
        sender, 12, f"<msg-{stored_path.name}@mail>", operation="submit_transcript",
        attachment_filename="meeting.vtt",
        attachment_storage_path=str(stored_path),
        meeting_date=datetime(2026, 8, 11, tzinfo=timezone.utc).isoformat(),
        meeting_date_source="vtt_note",
        speakers=speakers or ["Alice"],
    )
    job_store.set_status(job.job_id, JobState.VALIDATING)
    job_store.set_status(job.job_id, JobState.QUEUED)
    return job


def test_run_once_processes_all_queued_jobs(db_path: Path, tmp_path: Path):
    job_store = JobStore(db_path)
    storage = _storage(tmp_path)
    outbox = Outbox(db_path)
    admin = AdminNotifier(db_path, outbox, admin_email=None)
    fake_client = FakeDiarisationClient(
        groups=[GroupSummary(id=1, name="Team A")], member_by_name={"Alice": 101}
    )
    worker = JobWorker(
        job_store, fake_client, outbox, admin, storage, FakeGithubRaginatorClient(), StubLLM("{}")
    )

    job1 = _queued_job(job_store, storage)
    job2 = _queued_job(job_store, storage)

    processed_count = worker.run_once()

    assert processed_count == 2
    assert job_store.get(job1.job_id).status == JobState.COMPLETED
    assert job_store.get(job2.job_id).status == JobState.COMPLETED


def test_run_once_does_not_touch_non_queued_jobs(db_path: Path, tmp_path: Path):
    job_store = JobStore(db_path)
    storage = _storage(tmp_path)
    outbox = Outbox(db_path)
    admin = AdminNotifier(db_path, outbox, admin_email=None)
    fake_client = FakeDiarisationClient(groups=[GroupSummary(id=1, name="Team A")])
    worker = JobWorker(
        job_store, fake_client, outbox, admin, storage, FakeGithubRaginatorClient(), StubLLM("{}")
    )

    other_job = job_store.create_job("bob@uni.ac.uk", 7, "<other@mail>")  # stays RECEIVED

    assert worker.run_once() == 0
    assert job_store.get(other_job.job_id).status == JobState.RECEIVED


def test_one_failing_job_does_not_block_others(db_path: Path, tmp_path: Path):
    job_store = JobStore(db_path)
    storage = _storage(tmp_path)
    outbox = Outbox(db_path)
    admin = AdminNotifier(db_path, outbox, admin_email=None)
    fake_client = FakeDiarisationClient(
        groups=[GroupSummary(id=1, name="Team A")], member_by_name={"Alice": 101}, fail_on="create_meeting"
    )
    worker = JobWorker(
        job_store, fake_client, outbox, admin, storage, FakeGithubRaginatorClient(), StubLLM("{}")
    )

    job1 = _queued_job(job_store, storage)
    job2 = _queued_job(job_store, storage)

    worker.run_once()

    # Both fail (same fake client), but critically both were attempted - one failure doesn't
    # stop the loop from reaching the second job.
    assert job_store.get(job1.job_id).status == JobState.FAILED
    assert job_store.get(job2.job_id).status == JobState.FAILED


def test_run_forever_stops_promptly_on_stop_event(db_path: Path, tmp_path: Path):
    job_store = JobStore(db_path)
    storage = _storage(tmp_path)
    outbox = Outbox(db_path)
    admin = AdminNotifier(db_path, outbox, admin_email=None)
    fake_client = FakeDiarisationClient(groups=[])
    worker = JobWorker(
        job_store, fake_client, outbox, admin, storage, FakeGithubRaginatorClient(), StubLLM("{}")
    )

    stop_event = threading.Event()
    thread = threading.Thread(target=worker.run_forever, args=(0.05, stop_event))
    thread.start()
    stop_event.set()
    thread.join(timeout=2.0)
    assert not thread.is_alive()
