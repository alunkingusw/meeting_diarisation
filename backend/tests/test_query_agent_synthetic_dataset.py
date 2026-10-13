import json
import os
from collections import Counter
from datetime import datetime
from pathlib import Path

import pytest

from backend.transcript_rag.vtt_rag import process_vtt_file


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "query_agent_synthetic"


def _read_manifest():
    return json.loads((FIXTURE_DIR / "manifest.json").read_text(encoding="utf-8"))


def test_synthetic_vtt_files_produce_declared_speaker_statistics(tmp_path):
    manifest = _read_manifest()

    for meeting in manifest["meetings"]:
        result = process_vtt_file(
            file_path=str(FIXTURE_DIR / meeting["vtt_file"]),
            meeting_title=meeting["title"],
            meeting_date=meeting["date"],
            output_dir=str(tmp_path),
            meeting_id=str(meeting["id"]),
        )
        stats = json.loads(Path(result["stats_path"]).read_text(encoding="utf-8"))
        chunks = [
            json.loads(line)
            for line in Path(result["chunks_path"]).read_text(encoding="utf-8").splitlines()
        ]

        assert len(chunks) == meeting["expected_chunk_count"]
        assert stats["total_duration_sec"] == meeting["expected_stats"]["total_duration_sec"]
        actual_speakers = {item["speaker"]: item for item in stats["speakers"]}
        assert actual_speakers.keys() == meeting["expected_stats"]["speakers"].keys()
        for speaker, expected in meeting["expected_stats"]["speakers"].items():
            for metric, value in expected.items():
                assert actual_speakers[speaker][metric] == value
        chunk_ids = {chunk["chunk_id"] for chunk in chunks}
        for claim in meeting["gold_claims"]:
            assert set(claim["evidence"]) <= chunk_ids


@pytest.mark.skipif(
    os.environ.get("RUN_QUERY_AGENT_SEMANTIC_RETRIEVAL") != "1",
    reason="Set RUN_QUERY_AGENT_SEMANTIC_RETRIEVAL=1 to load the embedding model.",
)
def test_semantic_transcript_search_retrieves_gold_evidence_at_production_top_k(
    tmp_path, monkeypatch
):
    import chromadb

    from backend.config import settings
    from backend.transcript_rag import indexer, vectorstore

    manifest = _read_manifest()
    group_name = manifest["group"]["name"]
    collection_name = vectorstore.transcripts_collection_name(group_name)
    client = chromadb.PersistentClient(path=str(tmp_path / "semantic_chroma"))
    monkeypatch.setattr(vectorstore, "get_chroma_client", lambda: client)

    for meeting in manifest["meetings"]:
        processed = process_vtt_file(
            file_path=str(FIXTURE_DIR / meeting["vtt_file"]),
            meeting_title=meeting["title"],
            meeting_date=meeting["date"],
            output_dir=str(tmp_path / "processed" / str(meeting["id"])),
            meeting_id=str(meeting["id"]),
        )
        chunks = [
            json.loads(line)
            for line in Path(processed["chunks_path"]).read_text(encoding="utf-8").splitlines()
        ]
        vectorstore.replace_meeting_chunks(
            collection_name, meeting["id"], manifest["group"]["id"], chunks
        )

    retrieval_cases = [
        (12, "What decision did the team make about the API redesign?", "12_00000"),
        (12, "What rollback recommendation did Ada make?", "12_00002"),
        (13, "What did the monitoring dashboard show about the worker?", "13_00001"),
    ]
    reciprocal_ranks = []
    case_ranks = []
    misses = []
    for meeting_id, question, expected_id in retrieval_cases:
        hits = indexer.search_transcripts(
            group_name, question, n_results=settings.retrieval_top_k, meeting_id=meeting_id
        )
        ranks = [index + 1 for index, hit in enumerate(hits) if hit["chunk_id"] == expected_id]
        reciprocal_ranks.append(1 / ranks[0] if ranks else 0)
        case_ranks.append({"gold_id": expected_id, "rank": ranks[0] if ranks else None})
        if not ranks:
            misses.append(
                {
                    "question": question,
                    "expected_id": expected_id,
                    "k": settings.retrieval_top_k,
                    "ranked_ids": [hit["chunk_id"] for hit in hits],
                }
            )

    assert not misses, f"Gold evidence missed top-{settings.retrieval_top_k}: {misses}"
    mean_reciprocal_rank = sum(reciprocal_ranks) / len(reciprocal_ranks)
    print(
        f"Semantic transcript retrieval: Recall@{settings.retrieval_top_k}=1.0, "
        f"MRR@{settings.retrieval_top_k}={mean_reciprocal_rank:.3f}, ranks={case_ranks}"
    )
    assert mean_reciprocal_rank >= 0.5


def test_transcript_stats_loader_reports_missing_artifacts(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from backend.transcript_rag import indexer

    group_id = 44
    meeting = _read_manifest()["meetings"][0]
    stats_root = tmp_path / "transcripts" / str(group_id)
    process_vtt_file(
        file_path=str(FIXTURE_DIR / meeting["vtt_file"]),
        meeting_title=meeting["title"],
        meeting_date=meeting["date"],
        output_dir=str(stats_root),
        meeting_id=str(meeting["id"]),
    )
    monkeypatch.setattr(indexer, "settings", SimpleNamespace(EMBEDDING_DIR=tmp_path))

    records, missing = indexer.load_transcript_stats(group_id, [12, 13])

    assert [record["meeting_id"] for record in records] == ["12"]
    assert missing == [13]
    assert records[0]["speakers"][0]["speaker"] == "Ada"


def test_synthetic_project_activity_matches_declared_september_facts():
    manifest = _read_manifest()
    commits = [
        item for item in manifest["github_commits"]
        if datetime.fromisoformat(item["committed_at"].replace("Z", "+00:00")).strftime("%Y-%m") == "2026-09"
    ]
    actions = [
        item for item in manifest["trello_actions"]
        if datetime.fromisoformat(item["created_at"].replace("Z", "+00:00")).strftime("%Y-%m") == "2026-09"
    ]
    github_expected = manifest["expected_facts"]["github_september"]
    trello_expected = manifest["expected_facts"]["trello_september"]

    assert len(commits) == github_expected["total_commits"]
    assert dict(Counter(item["author_name"] for item in commits)) == github_expected["contributors"]
    assert sum(item["additions"] for item in commits) == github_expected["total_additions"]
    assert sum(item["deletions"] for item in commits) == github_expected["total_deletions"]
    assert len(actions) == trello_expected["total_actions"]
    assert dict(Counter(item["member_creator"] for item in actions)) == trello_expected["contributors"]


def test_synthetic_evaluation_cases_refer_to_supported_fixture_scope():
    manifest = _read_manifest()
    cases_path = Path(__file__).with_name("query_agent_eval_cases.json")
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    meeting_ids = {meeting["id"] for meeting in manifest["meetings"]}
    access = manifest["email_group_access"]
    group_ids = {manifest["group"]["id"]} | {
        group["id"] for group in manifest["additional_groups"]
    }

    assert meeting_ids == {12, 13}
    assert any(case["id"] == "conversation_speaker_metrics" for case in cases)
    assert any(case["id"] == "cross_source_mixed" for case in cases)
    assert set(access["accessible_group_ids"]) == group_ids
    assert access["inaccessible_group_id"] not in access["accessible_group_ids"]
    assert manifest["additional_groups"][0]["has_indexed_data"] is False
    for case in cases:
        if case.get("fixture_dataset_id"):
            assert case["fixture_dataset_id"] == manifest["dataset_id"]
        if case.get("fixture_meeting_id") is not None:
            assert case["fixture_meeting_id"] in meeting_ids

    speaker_case = next(case for case in cases if case["id"] == "conversation_speaker_metrics")
    assert speaker_case["expected_fact_values"] == {
        "speaker": "Ada", "talk_time_seconds": 150.0, "meeting_time_percent": 62.5
    }
    github_case = next(case for case in cases if case["id"] == "github_activity_counts")
    github_gold = manifest["expected_facts"]["github_september"]
    assert github_case["expected_fact_values"]["total_commits"] == github_gold["total_commits"]
    assert github_case["expected_fact_values"]["contributors"] == github_gold["contributors"]
    trello_case = next(case for case in cases if case["id"] == "trello_activity_counts")
    trello_gold = manifest["expected_facts"]["trello_september"]
    assert trello_case["expected_fact_values"]["total_actions"] == trello_gold["total_actions"]
    assert trello_case["expected_fact_values"]["contributors"] == trello_gold["contributors"]

    transcript_chunk_ids = {
        f"{meeting['id']}_{index:05d}"
        for meeting in manifest["meetings"]
        for index in range(meeting["expected_chunk_count"])
    }
    project_commit_ids = {
        f"{manifest['group']['repo_name']}:commit:{commit['sha']}"
        for commit in manifest["github_commits"]
    }
    expected_evidence_ids = transcript_chunk_ids | project_commit_ids
    for case in cases:
        assert set(case.get("expected_evidence_ids", [])) <= expected_evidence_ids