import pytest
from pydantic import ValidationError

from app.commands.schema import Operation, ParsedCommand


def test_minimal_valid_command():
    cmd = ParsedCommand(operation=Operation.HELP)
    assert cmd.operation == Operation.HELP
    assert cmd.attachment is None
    assert cmd.requires_clarification is False


def test_rejects_unknown_operation():
    with pytest.raises(ValidationError):
        ParsedCommand(operation="delete_everything")


def test_rejects_extra_fields_hallucinated_by_llm():
    with pytest.raises(ValidationError):
        ParsedCommand.model_validate(
            {
                "operation": "help",
                "shell_command": "rm -rf /",
            }
        )


@pytest.mark.parametrize(
    "bad_attachment",
    [
        "../../etc/passwd",
        "..\\..\\windows\\system32\\config",
        "/etc/passwd",
        "C:\\Windows\\System32\\config",
        "foo/bar.vtt",
        "foo\\bar.vtt",
    ],
)
def test_rejects_path_like_attachment(bad_attachment):
    with pytest.raises(ValidationError):
        ParsedCommand(operation=Operation.SUBMIT_TRANSCRIPT, attachment=bad_attachment)


def test_accepts_bare_filename_attachment():
    cmd = ParsedCommand(operation=Operation.SUBMIT_TRANSCRIPT, attachment="meeting.vtt")
    assert cmd.attachment == "meeting.vtt"


def test_rejects_bad_job_id_format():
    with pytest.raises(ValidationError):
        ParsedCommand(operation=Operation.STATUS, job_id="not-a-job-id")


def test_accepts_valid_job_id_format():
    cmd = ParsedCommand(operation=Operation.STATUS, job_id="DIAR-2026-0811-0017")
    assert cmd.job_id == "DIAR-2026-0811-0017"


def test_requires_clarification_question_when_flag_set():
    with pytest.raises(ValidationError):
        ParsedCommand(operation=Operation.HELP, requires_clarification=True)


def test_clarification_with_question_is_valid():
    cmd = ParsedCommand(
        operation=Operation.SUBMIT_TRANSCRIPT,
        requires_clarification=True,
        clarification_question="Which attachment did you mean?",
    )
    assert cmd.requires_clarification is True


def test_blank_strings_normalise_to_none():
    cmd = ParsedCommand(operation=Operation.HELP, group_hint="   ")
    assert cmd.group_hint is None


def test_assess_query_minimal_valid_with_one_source():
    cmd = ParsedCommand(operation=Operation.ASSESS_QUERY, github_focus="open issues")
    assert cmd.github_focus == "open issues"
    assert cmd.transcript_focus is None
    assert cmd.trello_focus is None


def test_assess_query_accepts_all_three_focus_fields():
    cmd = ParsedCommand(
        operation=Operation.ASSESS_QUERY,
        transcript_focus="mentions of the API redesign",
        github_focus="open issues about the API",
        trello_focus="cards tagged API",
    )
    assert cmd.transcript_focus == "mentions of the API redesign"
    assert cmd.github_focus == "open issues about the API"
    assert cmd.trello_focus == "cards tagged API"


def test_assess_query_blank_focus_fields_normalise_to_none():
    cmd = ParsedCommand(operation=Operation.ASSESS_QUERY, github_focus="   ", trello_focus="x")
    assert cmd.github_focus is None
    assert cmd.trello_focus == "x"
