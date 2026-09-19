from pathlib import Path

from app.jobs.store import JobStore
from app.mail.fake_client import make_test_email
from app.mail.thread_matcher import ThreadMatcher


def test_matches_via_in_reply_to_header(db_path: Path):
    store = JobStore(db_path)
    job = store.create_job("alice@uni.ac.uk", 12, "<original@fake>")
    store.update(job.job_id, last_response_message_id="<response-1@fake>")

    msg = make_test_email(
        "alice@uni.ac.uk", subject="Re: your job", in_reply_to="<response-1@fake>"
    )
    matcher = ThreadMatcher(store)
    assert matcher.match(msg, "alice@uni.ac.uk") == job.job_id


def test_in_reply_to_from_a_different_sender_does_not_match(db_path: Path):
    store = JobStore(db_path)
    job = store.create_job("alice@uni.ac.uk", 12, "<original@fake>")
    store.update(job.job_id, last_response_message_id="<response-1@fake>")

    msg = make_test_email(
        "mallory@evil.example", subject="Re: your job", in_reply_to="<response-1@fake>"
    )
    matcher = ThreadMatcher(store)
    assert matcher.match(msg, "mallory@evil.example") is None


def test_matches_via_single_job_id_in_subject(db_path: Path):
    store = JobStore(db_path)
    job = store.create_job("alice@uni.ac.uk", 12, "<original@fake>")

    msg = make_test_email("alice@uni.ac.uk", subject=f"Status of {job.job_id}?")
    matcher = ThreadMatcher(store)
    assert matcher.match(msg, "alice@uni.ac.uk") == job.job_id


def test_matches_via_single_job_id_in_body(db_path: Path):
    store = JobStore(db_path)
    job = store.create_job("alice@uni.ac.uk", 12, "<original@fake>")

    msg = make_test_email(
        "alice@uni.ac.uk", subject="Question", body_text=f"Can you cancel {job.job_id} please?"
    )
    matcher = ThreadMatcher(store)
    assert matcher.match(msg, "alice@uni.ac.uk") == job.job_id


def test_ambiguous_multiple_job_ids_does_not_match(db_path: Path):
    store = JobStore(db_path)
    job1 = store.create_job("alice@uni.ac.uk", 12, "<original1@fake>")
    job2 = store.create_job("alice@uni.ac.uk", 12, "<original2@fake>")

    msg = make_test_email(
        "alice@uni.ac.uk", subject="Question", body_text=f"{job1.job_id} or {job2.job_id}?"
    )
    matcher = ThreadMatcher(store)
    assert matcher.match(msg, "alice@uni.ac.uk") is None


def test_job_id_owned_by_someone_else_does_not_match(db_path: Path):
    store = JobStore(db_path)
    job = store.create_job("alice@uni.ac.uk", 12, "<original@fake>")

    msg = make_test_email("mallory@evil.example", subject=f"About {job.job_id}")
    matcher = ThreadMatcher(store)
    assert matcher.match(msg, "mallory@evil.example") is None


def test_no_references_at_all_returns_none(db_path: Path):
    store = JobStore(db_path)
    msg = make_test_email("alice@uni.ac.uk", subject="Hello", body_text="No job mentioned here.")
    matcher = ThreadMatcher(store)
    assert matcher.match(msg, "alice@uni.ac.uk") is None
