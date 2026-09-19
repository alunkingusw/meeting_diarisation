from app.email_templates import render

_INTERNAL_OPERATION_NAME = "submit_transcript"


def test_ack_never_exposes_internal_operation_name():
    subject, body = render.render_ack("DIAR-2026-0811-0001", "meeting.vtt", "2026-08-11", "Team A")
    assert "DIAR-2026-0811-0001" in subject
    assert "meeting.vtt" in body
    assert "Team A" in body
    assert _INTERNAL_OPERATION_NAME not in subject
    assert _INTERNAL_OPERATION_NAME not in body


def test_ack_without_group_name_omits_group_line():
    _, body = render.render_ack("DIAR-2026-0811-0001", "meeting.vtt", "2026-08-11", None)
    assert "Group:" not in body


def test_clarification_includes_the_question():
    subject, body = render.render_clarification("Which group is this for?")
    assert "Which group is this for?" in body
    assert _INTERNAL_OPERATION_NAME not in body


def test_failure_with_job_id():
    subject, body = render.render_failure("The file was empty.", job_id="DIAR-2026-0811-0002")
    assert "DIAR-2026-0811-0002" in subject
    assert "DIAR-2026-0811-0002" in body
    assert "The file was empty." in body


def test_failure_without_job_id_omits_job_line():
    subject, body = render.render_failure("No attachment found.")
    assert "Job ID" not in body
    assert "No attachment found." in body


def test_completion_lists_resolved_and_unresolved_speakers():
    _, body = render.render_completion(
        "DIAR-2026-0811-0003",
        "Team A",
        "2026-08-11",
        resolved_attendees=["Alice", "Bob"],
        unresolved_speakers=["Guest 1"],
    )
    assert "Alice" in body
    assert "Bob" in body
    assert "Guest 1" in body
    assert _INTERNAL_OPERATION_NAME not in body


def test_completion_with_no_unresolved_speakers_omits_that_section():
    _, body = render.render_completion(
        "DIAR-2026-0811-0003", "Team A", "2026-08-11", resolved_attendees=["Alice"],
        unresolved_speakers=[],
    )
    assert "could not be matched" not in body


def test_status_renders_job_id_and_status():
    subject, body = render.render_status("DIAR-2026-0811-0004", "Processing")
    assert "DIAR-2026-0811-0004" in subject
    assert "Processing" in body


def test_cancelled_confirms_job_id():
    subject, body = render.render_cancelled("DIAR-2026-0811-0005")
    assert "DIAR-2026-0811-0005" in subject
    assert "cancelled" in body.lower()


def test_cannot_cancel_explains_why():
    subject, body = render.render_cannot_cancel("DIAR-2026-0811-0006", "Completed")
    assert "already been processed" in body.lower()
    assert "Completed" in body


def test_help_mentions_vtt_and_rejects_audio_expectation():
    _, body = render.render_help()
    assert ".vtt" in body
    assert "audio" in body.lower()
    assert _INTERNAL_OPERATION_NAME not in body


def test_unrecognised_sender_includes_admin_contact():
    _, body = render.render_unrecognised_sender("admin@uni.ac.uk")
    assert "admin@uni.ac.uk" in body


def test_unrecognised_sender_without_admin_email_configured_still_renders():
    _, body = render.render_unrecognised_sender(None)
    assert "administrator" in body.lower()


def test_assess_ack_includes_job_id():
    _, body = render.render_assess_ack("DIAR-2026-0811-0017")
    assert "DIAR-2026-0811-0017" in body


def test_assess_result_includes_only_populated_sections():
    _, body = render.render_assess_result(
        "DIAR-2026-0811-0017",
        group_name="Team A",
        transcript_answer="Alice raised this in the 11 Aug meeting.",
        github_trello_answer=None,
        trello_checked=False,
        unavailable_notes=[],
    )
    assert "Alice raised this in the 11 Aug meeting." in body
    assert "GitHub" not in body


def test_assess_result_includes_unavailable_notes():
    _, body = render.render_assess_result(
        "DIAR-2026-0811-0017",
        group_name="Team A",
        transcript_answer=None,
        github_trello_answer="Bob opened issue #4.",
        trello_checked=False,
        unavailable_notes=["I couldn't check past meeting transcripts right now."],
    )
    assert "Bob opened issue #4." in body
    assert "couldn't check past meeting transcripts" in body
