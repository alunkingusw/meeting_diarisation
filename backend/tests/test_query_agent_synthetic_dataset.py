import json
from collections import Counter
from datetime import datetime
from pathlib import Path

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