from datetime import date
from types import SimpleNamespace

import pytest

from backend.engine.query_agent_schemas import SpecialistQueryInput, TrustedQueryContext
from backend.project_rag.schemas import (
    EvidenceItem,
    ProjectStatsResponse,
    SourceQueryResponse,
    TranscriptSpeakerStatsResponse,
    TranscriptStatsResponse,
)


class FakeSession:
    def __init__(self, group, repo=None):
        self.group = group
        self.repo = repo
        self.group_lookups = []
        self.rollbacks = 0

    def get(self, model, group_id):
        self.group_lookups.append((model, group_id))
        return self.group

    def rollback(self):
        self.rollbacks += 1

    def query(self, model):
        assert model.__name__ == "Repo"
        return FakeRepoQuery(self.repo)


class FakeRepoQuery:
    def __init__(self, repo):
        self.repo = repo

    def filter(self, condition):
        return self

    def one_or_none(self):
        return self.repo


def test_transcript_specialist_keeps_scope_and_structured_results(monkeypatch):
    from backend.engine import specialists

    group = SimpleNamespace(id=8, name="Team", github_repo_url=None, trello_board_id=None)
    repo = SimpleNamespace(id=16, name="Team")
    db = FakeSession(group, repo=repo)
    context = TrustedQueryContext(user_id=4, group_id=8, allowed_sources=["conversation"])
    request = SpecialistQueryInput(
        question="Who spoke most?",
        retrieval_question="Release discussion\nFollow-up: Who spoke most?",
        context="Prior turn context (reference resolution only, not evidence). Ada led the release.",
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
        truncated_evidence=0,
        complete_window=False,
        model_dump_json=lambda: "{\"source\":\"conversation\"}",
    )

    def fake_query_source(session, target_group, source, source_request):
        assert session is db
        assert target_group is group
        assert source == "conversation"
        assert source_request.question == request.retrieval_question
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
            user_content = state["messages"][0]["content"]
            assert request.question in user_content
            assert "Prior turn context" in user_content
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
    assert db.rollbacks == 1
    assert captured["tool"].args_schema.model_fields == {}


def test_transcript_specialist_rejects_untrusted_source_scope(monkeypatch):
    from backend.engine import specialists

    db = FakeSession(group=None)
    context = TrustedQueryContext(user_id=4, group_id=8, allowed_sources=["github"])
    request = SpecialistQueryInput(question="What did we decide?")

    with pytest.raises(PermissionError, match="not authorized"):
        specialists.run_transcript_specialist(db, context, request)

    assert db.group_lookups == []


def test_parent_composition_context_preserves_evidence_ids_facts_and_failures():
    from backend.engine.query_agent_schemas import QuantitativeFact, SpecialistQueryResult
    from backend.engine.query_graph import _compose_source_answers

    result = SpecialistQueryResult(
        source="github",
        question="How many September commits?",
        answer="Ada made four commits.",
        evidence=[
            EvidenceItem(
                id="group-8:commit-a1",
                source_type="github",
                author="Ada",
                timestamp="2026-09-12T10:00:00Z",
                text="Add release checklist",
            )
        ],
        quantitative_facts=[
            QuantitativeFact(
                name="commits",
                value=1,
                unit="count",
                scope={"group_id": 8, "since": "2026-09-01", "until": "2026-10-01"},
                provenance=["sql:commits:repo=8"],
                completeness="complete",
            )
        ],
    )

    answer = _compose_source_answers(
        {"github": result}, {"trello": "source is not linked"}
    )

    assert "GitHub findings:" in answer
    assert "Ada made four commits." in answer
    assert "Evidence IDs: [group-8:commit-a1]" in answer
    assert "Unavailable sources:\n- trello: unavailable" in answer


@pytest.mark.parametrize(
    ("source", "expected_fact", "expected_value"),
    [("github", "commits", 2), ("trello", "trello_actions", 3)],
)
def test_project_specialist_limits_tool_to_one_source_and_returns_facts(
    monkeypatch, source, expected_fact, expected_value
):
    from backend.engine import specialists

    group = SimpleNamespace(
        id=8,
        name="Team",
        github_repo_url="https://github.com/example/project" if source == "github" else None,
        trello_board_id="board-1" if source == "trello" else None,
    )
    repo = SimpleNamespace(id=16, name="Team")
    db = FakeSession(group, repo=repo)
    context = TrustedQueryContext(user_id=4, group_id=8, allowed_sources=[source])
    request = SpecialistQueryInput(
        question="Summarize activity",
        retrieval_question="API migration issue\nFollow-up: Summarize activity",
        filters={"since": "2026-09-01", "until": "2026-10-01"},
    )

    def fake_retrieve_question(session, target_repo, question, *, since, until, sources, label):
        assert session is db
        assert target_repo is repo
        assert question == request.retrieval_question
        assert since == date(2026, 9, 1)
        assert until == date(2026, 10, 1)
        assert sources == (source,)
        assert label == group.name
        return SimpleNamespace(
            stats=SimpleNamespace(
                repo_id=16,
                repo_name="Team",
                total_commits=2,
                total_issues=1,
                open_issues=1,
                closed_issues=0,
                total_issue_comments=0,
                total_review_comments=0,
                total_trello_actions=3,
                first_activity_at=None,
                last_activity_at=None,
                last_synced_at=None,
                contributors=[],
                weekly_activity=[],
            ),
            sources=[
                SimpleNamespace(
                    chunk_id=f"{source}-chunk-1",
                    source_type=source,
                    author="Ada",
                    timestamp="2026-09-30T10:00:00Z",
                    distance=0.1,
                    text="Activity",
                    metadata={},
                )
            ],
            truncated_sources=0,
            complete_window=True,
        )

    monkeypatch.setattr(specialists, "retrieve_question", fake_retrieve_question)
    monkeypatch.setattr(specialists, "ChatOllama", lambda **kwargs: kwargs)
    captured = {}

    class FakeAgent:
        def invoke(self, state):
            captured["tool"].invoke({})
            return {"messages": [SimpleNamespace(type="ai", content="Grounded answer.")]}

    def fake_create_agent(*, model, tools, system_prompt):
        captured["tool"] = tools[0]
        return FakeAgent()

    monkeypatch.setattr(specialists, "create_agent", fake_create_agent)

    result = (
        specialists.run_github_specialist(db, context, request)
        if source == "github"
        else specialists.run_trello_specialist(db, context, request)
    )

    assert result.source == source
    assert result.answer == "Grounded answer."
    assert result.evidence[0].id == f"{source}-chunk-1"
    assert any(
        fact.name == expected_fact and fact.value == expected_value
        for fact in result.quantitative_facts
    )
    assert result.quantitative_facts[0].completeness == "complete"
    assert captured["tool"].args_schema.model_fields == {}