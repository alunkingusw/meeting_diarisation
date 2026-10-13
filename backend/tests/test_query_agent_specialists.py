from datetime import date
from types import SimpleNamespace

import pytest

from backend.engine.query_agent_schemas import SpecialistQueryInput, TrustedQueryContext
from backend.project_rag.schemas import (
    EvidenceItem,
    TranscriptSpeakerStatsResponse,
    TranscriptStatsResponse,
)


class FakeSession:
    def __init__(self, group):
        self.group = group
        self.group_lookups = []
        self.rollbacks = 0

    def get(self, model, group_id):
        self.group_lookups.append((model, group_id))
        return self.group

    def rollback(self):
        self.rollbacks += 1


def test_transcript_specialist_keeps_scope_and_structured_results(monkeypatch):
    from backend.engine import specialists

    group = SimpleNamespace(id=8, name="Team", github_repo_url=None, trello_board_id=None)
    db = FakeSession(group)
    context = TrustedQueryContext(user_id=4, group_id=8, allowed_sources=["conversation"])
    request = SpecialistQueryInput(
        question="Who spoke most?",
        filters={"since": "2026-09-01", "until": "2026-10-01", "meeting_id": 42},
    )
    source_response = SimpleNamespace(
        source="conversation",
        evidence=[
            EvidenceItem(
                id="chunk-42-1",
                source_type="transcript",
                text="Ada proposed the release checklist.",
            )
        ],
        transcript_stats=TranscriptStatsResponse(
            complete=True,
            total_meetings=1,
            total_duration_sec=180.0,
            missing_meeting_ids=[],
            speakers=[
                TranscriptSpeakerStatsResponse(
                    speaker="Ada",
                    total_duration_sec=90.0,
                    total_words=30,
                    turn_count=4,
                    avg_words_per_turn=7.5,
                    meeting_time_share_pct=50.0,
                    meetings_spoken=1,
                )
            ],
            meetings=[],
        ),
        complete_window=False,
        model_dump_json=lambda: "{\"source\":\"conversation\"}",
    )

    def fake_query_source(session, target_group, source, source_request):
        assert session is db
        assert target_group is group
        assert source == "conversation"
        assert source_request.since == date(2026, 9, 1)
        assert source_request.until == date(2026, 10, 1)
        assert source_request.meeting_id == 42
        assert source_request.retrieve_only is True
        return source_response

    monkeypatch.setattr(specialists, "query_source", fake_query_source)
    monkeypatch.setattr(specialists, "ChatOllama", lambda **kwargs: kwargs)

    captured = {}

    class FakeAgent:
        def invoke(self, state):
            assert state["messages"][0]["content"] == request.question
            tool = captured["tool"]
            tool.invoke({})
            return {
                "messages": [
                    SimpleNamespace(type="ai", content="Ada spoke 90 seconds. [chunk-42-1]")
                ]
            }

    def fake_create_agent(*, model, tools, system_prompt):
        captured["tool"] = tools[0]
        captured["model"] = model
        captured["system_prompt"] = system_prompt
        return FakeAgent()

    monkeypatch.setattr(specialists, "create_agent", fake_create_agent)

    result = specialists.run_transcript_specialist(db, context, request)

    assert result.answer == "Ada spoke 90 seconds. [chunk-42-1]"
    assert result.evidence[0].id == "chunk-42-1"
    duration_fact = next(fact for fact in result.quantitative_facts if fact.name == "speaker_duration")
    assert duration_fact.value == 90.0
    assert duration_fact.scope == {
        "group_id": 8,
        "since": "2026-09-01",
        "until": "2026-10-01",
        "meeting_id": 42,
        "speaker": "Ada",
    }
    assert duration_fact.completeness == "complete"
    assert result.retrieval_metadata["transcript_stats_complete"] is True
    assert db.group_lookups[0][1] == 8
    assert db.rollbacks == 2
    assert captured["tool"].args_schema.model_fields == {}


def test_transcript_specialist_rejects_untrusted_source_scope(monkeypatch):
    from backend.engine import specialists

    db = FakeSession(group=None)
    context = TrustedQueryContext(user_id=4, group_id=8, allowed_sources=["github"])
    request = SpecialistQueryInput(question="What did we decide?")

    with pytest.raises(PermissionError, match="not authorized"):
        specialists.run_transcript_specialist(db, context, request)

    assert db.group_lookups == []