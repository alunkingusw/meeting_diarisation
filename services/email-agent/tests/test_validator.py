from pathlib import Path

import pytest

from app.commands.schema import Operation, ParsedCommand
from app.commands.validator import (
    AttachmentMeta,
    ClarificationRequired,
    Rejected,
    ValidationContext,
    validate_command,
)
from app.jobs.store import JobStore
from app.settings import LimitsSettings


def _ctx(db_path: Path, attachments=None, thread_job_id=None, sender_email="alice@uni.ac.uk",
          max_mb=20.0):
    return ValidationContext(
        attachments=attachments or [],
        thread_job_id=thread_job_id,
        sender_email=sender_email,
        job_store=JobStore(db_path),
        limits=LimitsSettings(max_attachment_size_mb=max_mb),
    )


def _vtt(filename="meeting.vtt", size=1000):
    return AttachmentMeta(filename=filename, size_bytes=size, content_type="text/vtt")


def _audio(filename="meeting.wav", size=1000):
    return AttachmentMeta(filename=filename, size_bytes=size, content_type="audio/wav")


# --- global: requires_clarification short-circuits everything ---

def test_llm_requested_clarification_is_honoured(db_path: Path):
    cmd = ParsedCommand(
        operation=Operation.SUBMIT_TRANSCRIPT,
        requires_clarification=True,
        clarification_question="Which meeting is this for?",
    )
    with pytest.raises(ClarificationRequired) as exc:
        validate_command(cmd, _ctx(db_path))
    assert exc.value.question == "Which meeting is this for?"


# --- submit_transcript: attachment resolution ---

def test_no_attachments_at_all_asks_for_clarification(db_path: Path):
    cmd = ParsedCommand(operation=Operation.SUBMIT_TRANSCRIPT)
    with pytest.raises(ClarificationRequired):
        validate_command(cmd, _ctx(db_path, attachments=[]))


def test_single_vtt_auto_selected_without_llm_naming_it(db_path: Path):
    cmd = ParsedCommand(operation=Operation.SUBMIT_TRANSCRIPT)
    result = validate_command(cmd, _ctx(db_path, attachments=[_vtt("meeting.vtt")]))
    assert result.attachment.filename == "meeting.vtt"


def test_llm_named_attachment_resolved_against_real_list(db_path: Path):
    cmd = ParsedCommand(operation=Operation.SUBMIT_TRANSCRIPT, attachment="meeting.vtt")
    ctx = _ctx(db_path, attachments=[_vtt("meeting.vtt"), _vtt("other.vtt")])
    result = validate_command(cmd, ctx)
    assert result.attachment.filename == "meeting.vtt"


def test_hallucinated_attachment_name_falls_back_to_real_single_candidate(db_path: Path):
    # The LLM claims a filename that isn't actually attached - since it's just a lookup key,
    # this must not be trusted; fall back to deterministic single-candidate resolution instead.
    cmd = ParsedCommand(operation=Operation.SUBMIT_TRANSCRIPT, attachment="not_really_there.vtt")
    ctx = _ctx(db_path, attachments=[_vtt("meeting.vtt")])
    result = validate_command(cmd, ctx)
    assert result.attachment.filename == "meeting.vtt"


def test_multiple_vtt_candidates_with_no_resolution_asks_for_clarification(db_path: Path):
    cmd = ParsedCommand(operation=Operation.SUBMIT_TRANSCRIPT)
    ctx = _ctx(db_path, attachments=[_vtt("meeting.vtt"), _vtt("other.vtt")])
    with pytest.raises(ClarificationRequired) as exc:
        validate_command(cmd, ctx)
    assert "meeting.vtt" in exc.value.question
    assert "other.vtt" in exc.value.question


def test_audio_only_attachment_is_rejected_not_clarified(db_path: Path):
    cmd = ParsedCommand(operation=Operation.SUBMIT_TRANSCRIPT)
    ctx = _ctx(db_path, attachments=[_audio("meeting.wav")])
    with pytest.raises(Rejected) as exc:
        validate_command(cmd, ctx)
    assert "audio" in str(exc.value).lower()
    assert "admin" in str(exc.value).lower()


def test_non_vtt_non_audio_attachment_asks_for_clarification(db_path: Path):
    cmd = ParsedCommand(operation=Operation.SUBMIT_TRANSCRIPT)
    ctx = _ctx(db_path, attachments=[AttachmentMeta("notes.pdf", 1000, "application/pdf")])
    with pytest.raises(ClarificationRequired):
        validate_command(cmd, ctx)


def test_oversized_vtt_is_rejected(db_path: Path):
    cmd = ParsedCommand(operation=Operation.SUBMIT_TRANSCRIPT)
    big = _vtt("meeting.vtt", size=5 * 1024 * 1024)
    ctx = _ctx(db_path, attachments=[big], max_mb=1.0)
    with pytest.raises(Rejected) as exc:
        validate_command(cmd, ctx)
    assert "too large" in str(exc.value).lower()


def test_group_hint_and_mentioned_date_pass_through(db_path: Path):
    cmd = ParsedCommand(
        operation=Operation.SUBMIT_TRANSCRIPT,
        group_hint="Tuesday Project Group",
        mentioned_date="last Tuesday",
    )
    ctx = _ctx(db_path, attachments=[_vtt()])
    result = validate_command(cmd, ctx)
    assert result.group_hint == "Tuesday Project Group"
    assert result.mentioned_date == "last Tuesday"


# --- status / results / cancel: job resolution ---

def test_no_job_id_and_no_thread_hint_asks_for_clarification(db_path: Path):
    cmd = ParsedCommand(operation=Operation.STATUS)
    with pytest.raises(ClarificationRequired):
        validate_command(cmd, _ctx(db_path))


def test_explicit_job_id_resolved_when_owned(db_path: Path):
    store = JobStore(db_path)
    job = store.create_job("alice@uni.ac.uk", 12, "<msg-1@mail>")
    cmd = ParsedCommand(operation=Operation.STATUS, job_id=job.job_id)
    ctx = _ctx(db_path, sender_email="alice@uni.ac.uk")
    result = validate_command(cmd, ctx)
    assert result.job_id == job.job_id


def test_job_id_belonging_to_someone_else_is_not_leaked(db_path: Path):
    store = JobStore(db_path)
    job = store.create_job("alice@uni.ac.uk", 12, "<msg-1@mail>")
    cmd = ParsedCommand(operation=Operation.STATUS, job_id=job.job_id)
    ctx = _ctx(db_path, sender_email="mallory@evil.example")
    with pytest.raises(ClarificationRequired):
        validate_command(cmd, ctx)


def test_thread_job_id_used_as_fallback(db_path: Path):
    store = JobStore(db_path)
    job = store.create_job("alice@uni.ac.uk", 12, "<msg-1@mail>")
    cmd = ParsedCommand(operation=Operation.RESULTS)
    ctx = _ctx(db_path, sender_email="alice@uni.ac.uk", thread_job_id=job.job_id)
    result = validate_command(cmd, ctx)
    assert result.job_id == job.job_id


def test_cancel_with_return_statistics_ignored_gracefully(db_path: Path):
    store = JobStore(db_path)
    job = store.create_job("alice@uni.ac.uk", 12, "<msg-1@mail>")
    cmd = ParsedCommand(operation=Operation.CANCEL, job_id=job.job_id, return_statistics=True)
    ctx = _ctx(db_path, sender_email="alice@uni.ac.uk")
    result = validate_command(cmd, ctx)
    assert result.operation == Operation.CANCEL
    assert result.job_id == job.job_id


# --- assess_query: dry-run source selection ---

def test_assess_query_single_source_validates_and_others_stay_none(db_path: Path):
    cmd = ParsedCommand(operation=Operation.ASSESS_QUERY, github_focus="open issues about auth")
    result = validate_command(cmd, _ctx(db_path))
    assert result.operation == Operation.ASSESS_QUERY
    assert result.github_focus == "open issues about auth"
    assert result.transcript_focus is None
    assert result.trello_focus is None


def test_assess_query_multiple_sources_all_pass_through(db_path: Path):
    cmd = ParsedCommand(
        operation=Operation.ASSESS_QUERY,
        transcript_focus="mentions of the API redesign",
        github_focus="open issues about the API",
        trello_focus="cards tagged API",
    )
    result = validate_command(cmd, _ctx(db_path))
    assert result.transcript_focus == "mentions of the API redesign"
    assert result.github_focus == "open issues about the API"
    assert result.trello_focus == "cards tagged API"


def test_assess_query_with_no_sources_asks_for_clarification(db_path: Path):
    cmd = ParsedCommand(operation=Operation.ASSESS_QUERY)
    with pytest.raises(ClarificationRequired):
        validate_command(cmd, _ctx(db_path))


def test_assess_query_group_hint_passes_through(db_path: Path):
    cmd = ParsedCommand(
        operation=Operation.ASSESS_QUERY,
        group_hint="Tuesday Project Group",
        trello_focus="open cards",
    )
    result = validate_command(cmd, _ctx(db_path))
    assert result.group_hint == "Tuesday Project Group"


def test_add_comment_requires_subject_ids_and_passes_comment(db_path: Path):
    cmd = ParsedCommand(operation=Operation.ADD_COMMENT, comment="Discuss the deadline.")
    ctx = _ctx(db_path)
    ctx.subject = "Re: Meeting summary group_id=7 meeting_id=42"
    result = validate_command(cmd, ctx)
    assert result.group_id == 7
    assert result.meeting_id == 42
    assert result.comment == "Discuss the deadline."


def test_add_comment_without_subject_ids_asks_for_clarification(db_path: Path):
    cmd = ParsedCommand(operation=Operation.ADD_COMMENT, comment="A note")
    with pytest.raises(ClarificationRequired):
        validate_command(cmd, _ctx(db_path))


# --- help ---

def test_help_needs_nothing_else(db_path: Path):
    cmd = ParsedCommand(operation=Operation.HELP)
    result = validate_command(cmd, _ctx(db_path))
    assert result.operation == Operation.HELP
