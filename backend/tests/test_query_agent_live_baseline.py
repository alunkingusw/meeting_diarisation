"""Opt-in live capture of the current query API against the synthetic corpus.

Run only when explicitly enabled; ordinary tests never call Ollama or write a baseline file.
"""
import json
import hashlib
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_QUERY_AGENT_LIVE_BASELINE") != "1",
    reason="Set RUN_QUERY_AGENT_LIVE_BASELINE=1 to call the configured Ollama service.",
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "query_agent_synthetic"


def _load_fixture_data():
    manifest = json.loads((FIXTURE_DIR / "manifest.json").read_text(encoding="utf-8"))
    cases = json.loads(Path(__file__).with_name("query_agent_eval_cases.json").read_text(encoding="utf-8"))
    return manifest, {case["id"]: case for case in cases}


def _seed_project_rows(db_session, group, manifest):
    from backend.project_rag import group_service
    from backend.project_rag.models import Commit, TrelloAction

    repo = group_service.get_or_create_repo(db_session, group)
    commits = [
        Commit(
            repo_id=repo.id,
            sha=item["sha"],
            author_name=item["author_name"],
            author_email=item["author_email"],
            committed_at=datetime.fromisoformat(item["committed_at"].replace("Z", "+00:00")),
            message=item["message"],
            files_changed=item["files_changed"],
            additions=item["additions"],
            deletions=item["deletions"],
            diff_text=item["diff_text"],
        )
        for item in manifest["github_commits"]
    ]
    actions = [
        TrelloAction(
            repo_id=repo.id,
            trello_action_id=item["trello_action_id"],
            action_type=item["action_type"],
            card_id=item["card_id"],
            card_name=item["card_name"],
            member_creator=item["member_creator"],
            text=item["text"],
            created_at=datetime.fromisoformat(item["created_at"].replace("Z", "+00:00")),
        )
        for item in manifest["trello_actions"]
    ]
    db_session.add_all(commits + actions)
    db_session.commit()


def _seed_transcript_chunks(monkeypatch, tmp_path, group, manifest):
    import chromadb

    from backend.transcript_rag import vectorstore
    from backend.transcript_rag.indexer import meeting_date_ts
    from backend.transcript_rag.vtt_rag import process_vtt_file

    client = chromadb.PersistentClient(path=str(tmp_path / "transcript_chroma"))
    monkeypatch.setattr(vectorstore, "get_chroma_client", lambda: client)
    collection_name = vectorstore.transcripts_collection_name(group.name)
    collection = client.get_or_create_collection(collection_name)

    for meeting in manifest["meetings"]:
        processed = process_vtt_file(
            file_path=str(FIXTURE_DIR / meeting["vtt_file"]),
            meeting_title=meeting["title"],
            meeting_date=meeting["date"],
            output_dir=str(tmp_path / "processed_vtt"),
            meeting_id=str(meeting["id"]),
        )
        chunks = [
            json.loads(line)
            for line in Path(processed["chunks_path"]).read_text(encoding="utf-8").splitlines()
        ]
        meeting_ts = meeting_date_ts(meeting["date"])
        for chunk in chunks:
            chunk["meeting_ts"] = meeting_ts
            chunk["group_id"] = group.id
        collection.upsert(
            ids=[chunk["chunk_id"] for chunk in chunks],
            documents=[chunk["text"] for chunk in chunks],
            metadatas=chunks,
            embeddings=[[0.0, 0.0, 0.0] for _ in chunks],
        )


def _sanitize(value):
    if isinstance(value, dict):
        return {
            key: Path(item).name if key == "source_file" and isinstance(item, str) else _sanitize(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def _capture(client, path, payload, auth_header):
    response = client.post(
        path,
        params={"run_async": "false"},
        json=payload,
        headers=auth_header,
    )
    try:
        body = response.json()
    except ValueError:
        body = {"text": response.text}
    return {
        "request": {"path": path, "payload": payload},
        "status_code": response.status_code,
        "body": _sanitize(body),
    }


def _compare_project_facts(case, capture, source):
    body = capture["body"]
    if source == "unified":
        body = body.get("results", {}).get("github", {})
    stats = body.get("stats") if isinstance(body, dict) else None
    expected = case.get("expected_fact_values")
    if not expected:
        return None
    if not stats:
        return {"expected": expected, "observed": None, "matches": False}

    if "total_commits" in expected:
        observed = {
            "total_commits": stats["total_commits"],
            "contributors": {item["name"]: item["commits"] for item in stats["contributors"]},
        }
    else:
        observed = {
            "total_actions": stats["total_trello_actions"],
            "contributors": {item["name"]: item["trello_actions"] for item in stats["contributors"]},
        }
    return {"expected": expected, "observed": observed, "matches": expected == observed}


def test_capture_live_query_baseline(
    client,
    db_session,
    make_user,
    auth_header_for,
    monkeypatch,
    tmp_path,
):
    output_value = os.environ.get("QUERY_AGENT_BASELINE_OUTPUT")
    if not output_value:
        pytest.fail("Set QUERY_AGENT_BASELINE_OUTPUT to an explicit JSON output path.")
    ollama_url = os.environ.get("OLLAMA_BASE_URL")
    if not ollama_url:
        pytest.fail("Set OLLAMA_BASE_URL to the reachable Ollama host.")

    from backend.models import Group, Meeting
    from backend.project_rag.models import Repo

    manifest, cases = _load_fixture_data()
    owner = make_user(username="synthetic-baseline-owner")
    group = Group(
        id=manifest["group"]["id"],
        name=manifest["group"]["name"],
        github_repo_url="https://example.invalid/synthetic/release",
        trello_board_id=manifest["group"]["trello_board_id"],
    )
    group.users.append(owner)
    db_session.add(group)
    for other_group in manifest["additional_groups"]:
        empty_group = Group(id=other_group["id"], name=other_group["name"])
        empty_group.users.append(owner)
        db_session.add(empty_group)
    db_session.add_all(
        [
            Meeting(
                id=meeting["id"],
                group_id=group.id,
                date=datetime.fromisoformat(f"{meeting['date']}T10:00:00"),
            )
            for meeting in manifest["meetings"]
        ]
    )
    db_session.commit()

    _seed_project_rows(db_session, group, manifest)
    _seed_transcript_chunks(monkeypatch, tmp_path, group, manifest)
    repo = db_session.query(Repo).filter_by(group_id=group.id).one()
    assert repo.name == manifest["group"]["repo_name"]

    auth_header = auth_header_for(owner.id)
    since_september = "2026-09-01"
    until_october = "2026-10-01"
    captures = {}

    for case_id in (
        "conversation_qualitative",
        "conversation_speaker_metrics",
        "conversation_mixed",
    ):
        case = cases[case_id]
        captures[case_id] = _capture(
            client,
            f"/groups/{group.id}/conversation/query",
            {
                "question": case["question"],
                "meeting_id": case.get("fixture_meeting_id"),
                "since": since_september,
                "until": until_october,
            },
            auth_header,
        )

    for case_id, source in (("github_activity_counts", "github"), ("trello_activity_counts", "trello")):
        case = cases[case_id]
        captures[case_id] = _capture(
            client,
            f"/groups/{group.id}/{source}/query",
            {"question": case["question"], **case.get("filters", {})},
            auth_header,
        )

    cross_case = cases["cross_source_mixed"]
    captures["cross_source_mixed"] = _capture(
        client,
        f"/groups/{group.id}/query",
        {
            "question": cross_case["question"],
            "since": since_september,
            "sources": cross_case["expected_sources"],
        },
        auth_header,
    )

    empty_case = cases["empty_evidence"]
    captures["empty_evidence"] = _capture(
        client,
        f"/groups/{group.id}/conversation/query",
        {
            "question": empty_case["question"],
            "meeting_id": empty_case["fixture_meeting_id"],
            **empty_case["filters"],
        },
        auth_header,
    )

    failed = {
        case_id: result
        for case_id, result in captures.items()
        if result["status_code"] not in ({"empty_evidence": {404}}.get(case_id, {200}))
    }
    assert not failed, f"Live baseline calls failed: {failed}"

    from backend.config import settings
    from backend.engine.query_graph import COMPOSE_SYSTEM_PROMPT, ROUTER_SYSTEM_PROMPT
    from backend.project_rag.group_service import CONVERSATION_SYSTEM_PROMPT
    from backend.project_rag.services.query_service import SYSTEM_PROMPT as PROJECT_SYSTEM_PROMPT
    import httpx

    tags = httpx.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags", timeout=10.0).json()
    model_info = next(
        (model for model in tags.get("models", []) if model.get("name") == settings.ollama_model),
        {},
    )
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    working_tree_dirty = bool(
        subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=True).stdout
    )
    project_case = cases["github_activity_counts"]
    trello_case = cases["trello_activity_counts"]
    cross_case = cases["cross_source_mixed"]

    artifact = {
        "dataset_id": manifest["dataset_id"],
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "code_revision": revision,
        "working_tree_dirty": working_tree_dirty,
        "ollama_endpoint_redacted": True,
        "ollama_model": settings.ollama_model,
        "ollama_model_digest": model_info.get("digest"),
        "ollama_quantization": (model_info.get("details") or {}).get("quantization_level"),
        "ollama_temperature": settings.ollama_temperature,
        "transcript_embedding_model": settings.TRANSCRIPT_EMBEDDING_MODEL_NAME,
        "transcript_retrieval_mode": "date-bounded complete Chroma window; fixture vectors are not used for similarity",
        "prompt_sha256": {
            "conversation": hashlib.sha256(CONVERSATION_SYSTEM_PROMPT.encode()).hexdigest(),
            "project": hashlib.sha256(PROJECT_SYSTEM_PROMPT.encode()).hexdigest(),
            "router": hashlib.sha256(ROUTER_SYSTEM_PROMPT.encode()).hexdigest(),
            "composer": hashlib.sha256(COMPOSE_SYSTEM_PROMPT.encode()).hexdigest(),
        },
        "cases": captures,
        "gold_comparisons": {
            "github_activity_counts": _compare_project_facts(
                project_case, captures["github_activity_counts"], "github"
            ),
            "trello_activity_counts": _compare_project_facts(
                trello_case, captures["trello_activity_counts"], "trello"
            ),
            "cross_source_mixed_github_stats": _compare_project_facts(
                cross_case, captures["cross_source_mixed"], "unified"
            ),
            "conversation_speaker_metrics": {
                "expected": cases["conversation_speaker_metrics"]["expected_fact_values"],
                "observed_structured_stats": captures["conversation_speaker_metrics"]["body"].get("stats"),
                "matches": False,
            },
        },
        "not_captured": ["authorization_ambiguity", "unsupported", "partial_source_failure"],
    }
    output_path = Path(output_value)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")