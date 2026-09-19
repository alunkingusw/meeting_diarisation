from pathlib import Path

from app.admin.notifier import AdminNotifier
from app.auth.authorisation import AuthSignals, SenderAuthoriser
from app.diarisation.client import GroupSummary
from app.jobs.models import JobState
from app.jobs.store import JobStore, Outbox, ProcessedMessageStore
from app.jobs.worker import JobWorker
from app.llm.command_parser import EmailCommandParser
from app.mail.base import Attachment
from app.mail.fake_client import FakeMailClient, make_test_email
from app.mail.thread_matcher import ThreadMatcher
from app.pipeline import EmailProcessingPipeline
from app.settings import LimitsSettings, StorageSettings

from app.github_raginator.client import RepoSummary
from tests.fakes import FakeDiarisationClient, FakeGithubRaginatorClient, StubLLM

FIXTURES = Path(__file__).parent / "fixtures" / "vtt"
PASS = AuthSignals(spf="pass", dkim="pass", dmarc="pass")

SUBMIT_TRANSCRIPT_JSON = (
    '{"operation": "submit_transcript", "attachment": "meeting.vtt", "group_hint": null, '
    '"job_id": null, "mentioned_date": null, "return_statistics": false, '
    '"requires_clarification": false, "clarification_question": null}'
)
HELP_JSON = (
    '{"operation": "help", "attachment": null, "group_hint": null, "job_id": null, '
    '"mentioned_date": null, "return_statistics": false, "requires_clarification": false, '
    '"clarification_question": null}'
)
ASSESS_QUERY_JSON = (
    '{"operation": "assess_query", "attachment": null, "group_hint": null, "job_id": null, '
    '"mentioned_date": null, "return_statistics": false, '
    '"transcript_focus": "mentions of the API redesign", "github_focus": "open API issues", '
    '"trello_focus": null, "requires_clarification": false, "clarification_question": null}'
)
ASSESS_QUERY_NO_SOURCES_JSON = (
    '{"operation": "assess_query", "attachment": null, "group_hint": null, "job_id": null, '
    '"mentioned_date": null, "return_statistics": false, '
    '"transcript_focus": null, "github_focus": null, "trello_focus": null, '
    '"requires_clarification": false, "clarification_question": null}'
)


def _vtt_attachment(fixture="valid_with_date.vtt", filename="meeting.vtt"):
    return Attachment(filename=filename, content_type="text/vtt", content=(FIXTURES / fixture).read_bytes())


def _build_pipeline(db_path: Path, tmp_path: Path, mail_client, llm_response, admin_email="admin@uni.ac.uk",
                     group_owners=None, authorised_domains=None, available=True):
    job_store = JobStore(db_path)
    processed_store = ProcessedMessageStore(db_path)
    outbox = Outbox(db_path)
    admin = AdminNotifier(db_path, outbox, admin_email=admin_email)
    authoriser = SenderAuthoriser(
        group_owners or {"alice@uni.ac.uk": 12},
        authorised_domains or ["uni.ac.uk"],
    )
    stub_llm = StubLLM(llm_response, available=available)
    parser = EmailCommandParser(stub_llm, max_retries=1)
    thread_matcher = ThreadMatcher(job_store)
    storage = StorageSettings(
        incoming=tmp_path / "incoming", processing=tmp_path / "processing",
        completed=tmp_path / "completed", failed=tmp_path / "failed", db_path=db_path,
    )
    limits = LimitsSettings(max_attachment_size_mb=20, allowed_attachment_extensions=[".vtt"])

    pipeline = EmailProcessingPipeline(
        mail_client, authoriser, stub_llm, parser, job_store, processed_store, outbox, admin,
        thread_matcher, storage, limits, admin_email,
    )
    return pipeline, job_store, outbox, admin, storage, stub_llm


def _worker(
    job_store, storage, outbox, admin, groups, member_by_name=None, transcript_chunks=None,
    github_raginator_client=None, ollama_client=None,
):
    fake_client = FakeDiarisationClient(
        groups=groups, member_by_name=member_by_name or {}, transcript_chunks=transcript_chunks
    )
    worker = JobWorker(
        job_store, fake_client, outbox, admin, storage,
        github_raginator_client or FakeGithubRaginatorClient(),
        ollama_client or StubLLM("A synthesised answer."),
    )
    return worker, fake_client


def test_full_happy_path_submit_transcript_end_to_end(db_path: Path, tmp_path: Path):
    mail = FakeMailClient()
    msg = make_test_email(
        "alice@uni.ac.uk", subject="Transcript", body_text="Please add this transcript.",
        attachments=[_vtt_attachment()], auth_signals=PASS,
    )
    mail.add_message(msg)

    pipeline, job_store, outbox, admin, storage, _ = _build_pipeline(
        db_path, tmp_path, mail, SUBMIT_TRANSCRIPT_JSON
    )

    processed = pipeline.poll_once()
    assert processed == 1

    jobs = job_store.list_queued()
    assert len(jobs) == 1
    job = jobs[0]
    assert job.status == JobState.QUEUED

    worker, fake_client = _worker(job_store, storage, outbox, admin, groups=[GroupSummary(id=1, name="Team A")],
                                   member_by_name={"Alice": 101, "Bob": 102})
    worker.run_once()

    assert job_store.get(job.job_id).status == JobState.COMPLETED

    sent_count = pipeline.flush_outbox()
    assert sent_count == 2  # ack + completion
    subjects = [m.subject for m in mail.sent]
    assert any("received" in s.lower() for s in subjects)
    assert any("processed" in s.lower() for s in subjects)
    assert all(m.to == "alice@uni.ac.uk" for m in mail.sent)


def test_duplicate_message_id_never_creates_two_jobs(db_path: Path, tmp_path: Path):
    mail = FakeMailClient()
    # Simulates provider-side redelivery: same Message-ID, two distinct provider entries.
    msg1 = make_test_email(
        "alice@uni.ac.uk", message_id="<same@mail>", attachments=[_vtt_attachment()], auth_signals=PASS,
    )
    msg1.provider_ref = "provider-ref-1"
    msg2 = make_test_email(
        "alice@uni.ac.uk", message_id="<same@mail>", attachments=[_vtt_attachment()], auth_signals=PASS,
    )
    msg2.provider_ref = "provider-ref-2"
    mail.add_message(msg1)
    mail.add_message(msg2)

    pipeline, job_store, outbox, admin, storage, _ = _build_pipeline(db_path, tmp_path, mail, SUBMIT_TRANSCRIPT_JSON)
    pipeline.poll_once()

    assert len(job_store.list_queued()) == 1
    # Both provider entries must be marked processed so neither resurfaces.
    assert mail.fetch_new_messages() == []


def test_unauthorised_external_sender_is_silently_dropped(db_path: Path, tmp_path: Path):
    mail = FakeMailClient()
    msg = make_test_email("mallory@evil.example", auth_signals=PASS)
    mail.add_message(msg)

    pipeline, job_store, outbox, admin, storage, _ = _build_pipeline(db_path, tmp_path, mail, HELP_JSON)
    pipeline.poll_once()
    pipeline.flush_outbox()

    # No reply to the external sender - but the admin still hears about the attempt (both are
    # delivered through the same MailClient, so mail.sent legitimately contains the alert).
    assert all(m.to != "mallory@evil.example" for m in mail.sent)
    assert job_store.list_queued() == []
    assert any(m.to == "admin@uni.ac.uk" for m in mail.sent)


def test_unrecognised_in_domain_sender_gets_friendly_reply(db_path: Path, tmp_path: Path):
    mail = FakeMailClient()
    msg = make_test_email("carol@uni.ac.uk", auth_signals=PASS)
    mail.add_message(msg)

    pipeline, job_store, outbox, admin, storage, _ = _build_pipeline(db_path, tmp_path, mail, HELP_JSON)
    pipeline.poll_once()
    pipeline.flush_outbox()

    # Both the friendly reply to carol and the admin heads-up are delivered.
    assert len(mail.sent) == 2
    carol_msg = next(m for m in mail.sent if m.to == "carol@uni.ac.uk")
    assert "isn't currently registered" in carol_msg.body_text.lower()
    assert any(m.to == "admin@uni.ac.uk" for m in mail.sent)
    assert job_store.list_queued() == []


def test_ambiguous_group_produces_clarification_after_worker_run(db_path: Path, tmp_path: Path):
    mail = FakeMailClient()
    msg = make_test_email(
        "alice@uni.ac.uk", attachments=[_vtt_attachment()], auth_signals=PASS,
    )
    mail.add_message(msg)

    pipeline, job_store, outbox, admin, storage, _ = _build_pipeline(db_path, tmp_path, mail, SUBMIT_TRANSCRIPT_JSON)
    pipeline.poll_once()
    job = job_store.list_queued()[0]

    worker, _ = _worker(
        job_store, storage, outbox, admin,
        groups=[GroupSummary(id=1, name="Team A"), GroupSummary(id=2, name="Team B")],
    )
    worker.run_once()

    assert job_store.get(job.job_id).status == JobState.NEEDS_CLARIFICATION
    pipeline.flush_outbox()
    assert any("Team A" in m.body_text and "Team B" in m.body_text for m in mail.sent)


def test_clarification_reply_requeues_and_completes_same_job(db_path: Path, tmp_path: Path):
    mail = FakeMailClient()
    original = make_test_email(
        "alice@uni.ac.uk", message_id="<original-transcript@mail>",
        attachments=[_vtt_attachment()], auth_signals=PASS,
    )
    mail.add_message(original)

    pipeline, job_store, outbox, admin, storage, stub_llm = _build_pipeline(
        db_path, tmp_path, mail, SUBMIT_TRANSCRIPT_JSON
    )
    pipeline.poll_once()
    job = job_store.list_queued()[0]
    pipeline.flush_outbox()

    worker, _ = _worker(
        job_store, storage, outbox, admin,
        groups=[GroupSummary(id=1, name="Team A"), GroupSummary(id=2, name="Team B")],
    )
    worker.run_once()
    assert job_store.get(job.job_id).status == JobState.NEEDS_CLARIFICATION
    pipeline.flush_outbox()

    clarification = mail.sent[-1]
    assert job.job_id in clarification.subject
    assert clarification.in_reply_to == original.message_id
    assert clarification.references == original.message_id

    reply = make_test_email(
        "alice@uni.ac.uk", message_id="<group-answer@mail>", body_text="Team A",
        in_reply_to=clarification.id, references=clarification.id, auth_signals=PASS,
    )
    mail.add_message(reply)
    pipeline.poll_once()

    assert job_store.get(job.job_id).status == JobState.QUEUED
    assert job_store.get(job.job_id).group_hint == "Team A"
    assert stub_llm.calls == 1
    pipeline.flush_outbox()
    assert mail.sent[-1].in_reply_to == reply.message_id
    assert mail.sent[-1].references == clarification.id + " " + reply.message_id

    worker, fake_client = _worker(
        job_store, storage, outbox, admin,
        groups=[GroupSummary(id=1, name="Team A"), GroupSummary(id=2, name="Team B")],
        member_by_name={"Alice": 101, "Bob": 102},
    )
    worker.run_once()
    assert job_store.get(job.job_id).status == JobState.COMPLETED
    assert len(job_store.list_queued()) == 0
    pipeline.flush_outbox()
    assert any(job.job_id in message.subject and "processed" in message.subject.lower() for message in mail.sent)


def test_ollama_unavailable_defers_message_without_marking_it_processed(db_path: Path, tmp_path: Path):
    mail = FakeMailClient()
    msg = make_test_email("alice@uni.ac.uk", attachments=[_vtt_attachment()], auth_signals=PASS)
    mail.add_message(msg)

    pipeline, job_store, outbox, admin, storage, stub_llm = _build_pipeline(
        db_path, tmp_path, mail, SUBMIT_TRANSCRIPT_JSON, available=False
    )
    pipeline.poll_once()

    assert job_store.list_queued() == []
    assert mail.fetch_new_messages() == [msg]  # still there for the next poll
    assert len(outbox.pending()) == 1  # the infrastructure admin alert


def test_llm_parse_failure_sends_clarification_and_admin_alert(db_path: Path, tmp_path: Path):
    mail = FakeMailClient()
    msg = make_test_email("alice@uni.ac.uk", body_text="garbled request", auth_signals=PASS)
    mail.add_message(msg)

    pipeline, job_store, outbox, admin, storage, _ = _build_pipeline(
        db_path, tmp_path, mail, "not valid json at all"
    )
    pipeline.poll_once()
    pipeline.flush_outbox()

    assert job_store.list_queued() == []
    recipients = {m.to for m in mail.sent}
    assert "alice@uni.ac.uk" in recipients
    assert "admin@uni.ac.uk" in recipients


def test_assess_query_end_to_end_sends_ack_then_answer(db_path: Path, tmp_path: Path):
    mail = FakeMailClient()
    msg = make_test_email(
        "alice@uni.ac.uk",
        body_text="Have we discussed the API redesign, and are there any related GitHub issues?",
        auth_signals=PASS,
    )
    mail.add_message(msg)

    pipeline, job_store, outbox, admin, storage, _ = _build_pipeline(db_path, tmp_path, mail, ASSESS_QUERY_JSON)
    pipeline.poll_once()
    pipeline.flush_outbox()

    assert len(mail.sent) == 1
    assert "job id" in mail.sent[0].body_text.lower()
    job = job_store.list_queued()[0]
    assert job.operation == "assess_query"
    assert job.transcript_focus == "mentions of the API redesign"
    assert job.github_focus == "open API issues"

    worker, _ = _worker(
        job_store, storage, outbox, admin, groups=[GroupSummary(id=1, name="Team A")],
        transcript_chunks=[],
        github_raginator_client=FakeGithubRaginatorClient(
            repo_by_group_name={"Team A": RepoSummary(id=1, github_url="https://github.com/org/repo", group_name="Team A")},
            answer="Alice opened issue #12 about the API redesign.",
        ),
    )
    worker.run_once()
    pipeline.flush_outbox()

    assert job_store.get(job.job_id).status == JobState.COMPLETED
    assert len(mail.sent) == 2
    body = mail.sent[1].body_text
    assert "Alice opened issue #12 about the API redesign." in body


def test_assess_query_with_no_sources_sends_clarification(db_path: Path, tmp_path: Path):
    mail = FakeMailClient()
    msg = make_test_email("alice@uni.ac.uk", body_text="Can you help with this?", auth_signals=PASS)
    mail.add_message(msg)

    pipeline, job_store, outbox, admin, storage, _ = _build_pipeline(
        db_path, tmp_path, mail, ASSESS_QUERY_NO_SOURCES_JSON
    )
    pipeline.poll_once()
    pipeline.flush_outbox()

    assert len(mail.sent) == 1
    assert "clarif" in mail.sent[0].subject.lower()


def test_audio_attachment_is_rejected_without_an_admin_alert(db_path: Path, tmp_path: Path):
    mail = FakeMailClient()
    audio_json = (
        '{"operation": "submit_transcript", "attachment": "meeting.wav", "group_hint": null, '
        '"job_id": null, "mentioned_date": null, "return_statistics": false, '
        '"requires_clarification": false, "clarification_question": null}'
    )
    msg = make_test_email(
        "alice@uni.ac.uk",
        attachments=[Attachment(filename="meeting.wav", content_type="audio/wav", content=b"RIFF....")],
        auth_signals=PASS,
    )
    mail.add_message(msg)

    pipeline, job_store, outbox, admin, storage, _ = _build_pipeline(db_path, tmp_path, mail, audio_json)
    pipeline.poll_once()
    pipeline.flush_outbox()

    assert job_store.list_queued() == []
    assert len(mail.sent) == 1  # only the sender gets a rejection - no admin alert for this
    assert mail.sent[0].to == "alice@uni.ac.uk"
    assert "audio" in mail.sent[0].body_text.lower()
