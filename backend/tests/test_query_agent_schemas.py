import pytest
from pydantic import ValidationError

from backend.engine.query_agent_schemas import (
    QuantitativeFact,
    QueryFilters,
    SpecialistQueryInput,
    SpecialistQueryResult,
    TrustedQueryContext,
)


def test_specialist_input_excludes_trusted_identity_and_group_scope():
    request = SpecialistQueryInput(question="Who spoke most?", filters={"meeting_id": 12})

    assert request.filters.meeting_id == 12
    with pytest.raises(ValidationError):
        SpecialistQueryInput(question="Who spoke most?", group_id=4)


def test_query_filters_use_exclusive_until_and_reject_empty_ranges():
    assert QueryFilters(since="2026-09-01", until="2026-10-01").until.isoformat() == "2026-10-01"
    with pytest.raises(ValidationError):
        QueryFilters(since="2026-10-01", until="2026-10-01")


def test_quantitative_fact_requires_scope_provenance_and_completeness():
    fact = QuantitativeFact(
        name="speaker_talk_time",
        value=125.5,
        unit="seconds",
        scope={"group_id": 4, "meeting_id": 12},
        provenance=["transcript_stats:meeting=12"],
        completeness="complete",
    )

    assert fact.value == 125.5
    assert fact.completeness == "complete"
    with pytest.raises(ValidationError):
        QuantitativeFact(name="commits", value=2, unit="count", scope={}, provenance=[])


def test_specialist_result_carries_facts_and_evidence_separately():
    result = SpecialistQueryResult(
        source="conversation",
        question="Who spoke most, and what did they recommend?",
        answer="The transcript evidence supports the recommendation.",
        quantitative_facts=[
            QuantitativeFact(
                name="speaker_talk_time",
                value=125.5,
                unit="seconds",
                scope={"meeting_id": 12},
                provenance=["transcript_stats:meeting=12"],
                completeness="complete",
            )
        ],
    )

    assert result.quantitative_facts[0].name == "speaker_talk_time"
    assert result.evidence == []


def test_trusted_context_is_application_scoped():
    context = TrustedQueryContext(user_id=7, group_id=4, allowed_sources=["conversation"])

    assert context.group_id == 4
    with pytest.raises(ValidationError):
        context.group_id = 9