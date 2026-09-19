import pytest

from app.commands.schema import CommandParsingFailed, Operation
from app.llm.command_parser import EmailCommandParser


class StubOllama:
    """Returns queued responses in order; repeats the last one once exhausted."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.0) -> str:
        self.calls.append((system_prompt, user_prompt))
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]


def test_valid_json_on_first_try():
    stub = StubOllama([
        '{"operation": "help", "attachment": null, "group_hint": null, "job_id": null, '
        '"mentioned_date": null, "return_statistics": false, "requires_clarification": false, '
        '"clarification_question": null}'
    ])
    parser = EmailCommandParser(stub, max_retries=2)
    cmd = parser.parse_email("What can you do?", [])
    assert cmd.operation == Operation.HELP
    assert len(stub.calls) == 1


def test_invalid_json_then_valid_on_retry_succeeds():
    stub = StubOllama([
        "not json at all",
        '{"operation": "help", "attachment": null, "group_hint": null, "job_id": null, '
        '"mentioned_date": null, "return_statistics": false, "requires_clarification": false, '
        '"clarification_question": null}',
    ])
    parser = EmailCommandParser(stub, max_retries=2)
    cmd = parser.parse_email("hi", [])
    assert cmd.operation == Operation.HELP
    assert len(stub.calls) == 2
    # the retry attempt should have used a corrective system prompt
    assert "previous response" in stub.calls[1][0].lower()


def test_schema_invalid_json_then_valid_on_retry_succeeds():
    stub = StubOllama([
        '{"operation": "not_a_real_operation"}',
        '{"operation": "help", "attachment": null, "group_hint": null, "job_id": null, '
        '"mentioned_date": null, "return_statistics": false, "requires_clarification": false, '
        '"clarification_question": null}',
    ])
    parser = EmailCommandParser(stub, max_retries=2)
    cmd = parser.parse_email("hi", [])
    assert cmd.operation == Operation.HELP


def test_exhausted_retries_raises_command_parsing_failed_never_a_default_command():
    stub = StubOllama(["still not json", "still not json"])
    parser = EmailCommandParser(stub, max_retries=1)
    with pytest.raises(CommandParsingFailed):
        parser.parse_email("hi", [])
    assert len(stub.calls) == 2  # initial attempt + 1 retry


def test_body_is_truncated_before_prompting():
    stub = StubOllama([
        '{"operation": "help", "attachment": null, "group_hint": null, "job_id": null, '
        '"mentioned_date": null, "return_statistics": false, "requires_clarification": false, '
        '"clarification_question": null}'
    ])
    parser = EmailCommandParser(stub, max_retries=0, max_body_chars=10)
    parser.parse_email("x" * 1000, [])
    _, user_prompt = stub.calls[0]
    assert "x" * 1000 not in user_prompt
    assert "x" * 10 in user_prompt


def test_attachment_filenames_included_in_prompt():
    stub = StubOllama([
        '{"operation": "submit_transcript", "attachment": "meeting.vtt", "group_hint": null, '
        '"job_id": null, "mentioned_date": null, "return_statistics": false, '
        '"requires_clarification": false, "clarification_question": null}'
    ])
    parser = EmailCommandParser(stub, max_retries=0)
    cmd = parser.parse_email("please process meeting.vtt", ["meeting.vtt", "other.wav"])
    assert cmd.attachment == "meeting.vtt"
    _, user_prompt = stub.calls[0]
    assert "meeting.vtt" in user_prompt
    assert "other.wav" in user_prompt
