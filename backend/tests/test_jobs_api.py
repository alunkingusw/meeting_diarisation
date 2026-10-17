from datetime import datetime

import pytest


class SyncPool:
    """Runs submitted jobs immediately so tests are deterministic."""

    def submit(self, fn, *args):
        fn(*args)


@pytest.fixture
def sync_jobs(monkeypatch):
    from backend.jobs import service

    monkeypatch.setattr(service, "_executor", SyncPool())
    return service


def _team(db_session, make_user, make_group):
    owner = make_user(username="owner")
    group = make_group(name="Team A", owner=owner)
    return owner, group


def test_job_lifecycle_completed_and_failed(sync_jobs, client, db_session, make_user, make_group, auth_header_for):
    from backend.jobs.service import handler, submit_job

    @handler("test_ok")
    def ok(ctx, params):
        ctx.progress("halfway")
        return {"echo": params["x"]}

    @handler("test_boom")
    def boom(ctx, params):
        raise RuntimeError("it broke")

    owner, group = _team(db_session, make_user, make_group)
    good = submit_job(db_session, "test_ok", {"x": 5}, user_id=owner.id, group_id=group.id)
    bad = submit_job(db_session, "test_boom", {}, user_id=owner.id, group_id=group.id)

    done = client.get(f"/jobs/{good.id}", headers=auth_header_for(owner.id)).json()
    assert done["state"] == "completed" and done["result"] == {"echo": 5} and done["progress"] == "halfway"
    assert done["started_at"] and done["finished_at"]
    failed = client.get(f"/jobs/{bad.id}", headers=auth_header_for(owner.id)).json()
    assert failed["state"] == "failed" and failed["error"] == "it broke" and failed["error_type"] == "RuntimeError"


def test_queued_job_cancels_immediately_and_never_runs(client, db_session, make_user, make_group, auth_header_for, monkeypatch):
    from backend.jobs import service

    class DeferredPool:
        def __init__(self):
            self.pending = []

        def submit(self, fn, *args):
            self.pending.append((fn, args))

    pool = DeferredPool()
    monkeypatch.setattr(service, "_executor", pool)
    ran = []
    service.handler("test_defer")(lambda ctx, params: ran.append(1))
    owner, group = _team(db_session, make_user, make_group)
    job = service.submit_job(db_session, "test_defer", {}, user_id=owner.id, group_id=group.id)

    cancelled = client.post(f"/jobs/{job.id}/cancel", headers=auth_header_for(owner.id))
    for fn, args in pool.pending:
        fn(*args)

    assert cancelled.status_code == 200 and cancelled.json()["state"] == "cancelled"
    assert ran == []
    again = client.post(f"/jobs/{job.id}/cancel", headers=auth_header_for(owner.id))
    assert again.status_code == 409


def test_running_job_stops_at_next_checkpoint_when_cancelled(sync_jobs, client, db_session, make_user, make_group, auth_header_for):
    from backend.jobs.service import handler, submit_job
    from backend.models import Job

    owner, group = _team(db_session, make_user, make_group)

    @handler("test_cooperative")
    def cooperative(ctx, params):
        ctx.progress("step 1")
        client.post(f"/jobs/{ctx.job_id}/cancel", headers=auth_header_for(owner.id))
        ctx.check_cancelled()
        return {"reached": "unexpected"}

    job = submit_job(db_session, "test_cooperative", {}, user_id=owner.id, group_id=group.id)

    db_session.expire_all()
    stored = db_session.get(Job, job.id)
    assert stored.state == "cancelled" and stored.result is None


def test_jobs_are_visible_to_creator_and_group_owner_only(sync_jobs, client, db_session, make_user, make_group, auth_header_for):
    from backend.jobs.service import handler, submit_job

    handler("test_visible")(lambda ctx, params: {})
    owner, group = _team(db_session, make_user, make_group)
    member = make_user(username="member")
    group.users.append(member)
    db_session.commit()
    outsider = make_user(username="outsider")
    job = submit_job(db_session, "test_visible", {}, user_id=member.id, group_id=group.id)

    assert client.get(f"/jobs/{job.id}", headers=auth_header_for(member.id)).status_code == 200
    assert client.get(f"/jobs/{job.id}", headers=auth_header_for(owner.id)).status_code == 200
    assert client.get(f"/jobs/{job.id}", headers=auth_header_for(outsider.id)).status_code == 404
    listed = client.get("/jobs/", headers=auth_header_for(outsider.id)).json()
    assert listed == []
    assert [j["id"] for j in client.get("/jobs/?kind=test_visible", headers=auth_header_for(owner.id)).json()] == [job.id]


def test_interrupted_jobs_are_marked_failed_on_recovery(db_session, make_user, make_group):
    from backend.jobs.service import recover_interrupted
    from backend.models import Job

    owner, group = _team(db_session, make_user, make_group)
    db_session.add_all([
        Job(id="j-run", kind="x", state="running", params={}, user_id=owner.id),
        Job(id="j-done", kind="x", state="completed", params={}, user_id=owner.id),
    ])
    db_session.commit()

    assert recover_interrupted() == 1

    db_session.expire_all()
    assert db_session.get(Job, "j-run").state == "failed"
    assert db_session.get(Job, "j-run").error == "Interrupted by a restart"
    assert db_session.get(Job, "j-done").state == "completed"


def test_async_query_returns_202_and_result_lands_on_the_job(
    sync_jobs, client, db_session, make_user, make_group, auth_header_for, monkeypatch, fake_llm
):
    from backend.project_rag import group_service

    owner, group = _team(db_session, make_user, make_group)
    chunk = {
        "chunk_id": "1_0", "meeting_id": "1", "meeting_title": "Team A", "meeting_date": "2026-10-01",
        "speaker": "Bob", "text": "We agreed.", "start_ts": "00:00:01.000", "end_ts": "00:00:09.000",
    }
    monkeypatch.setattr(group_service, "search_transcripts", lambda *a, **k: [chunk])

    accepted = client.post(
        f"/groups/{group.id}/conversation/query?async=true",
        json={"question": "What was agreed?"}, headers=auth_header_for(owner.id),
    )

    assert accepted.status_code == 202
    job = client.get(f"/jobs/{accepted.json()['job_id']}", headers=auth_header_for(owner.id)).json()
    assert job["state"] == "completed" and job["kind"] == "query"
    assert job["result"]["answer"] == "fake answer" and job["result"]["source"] == "conversation"


def test_async_unified_query_runs_parent_with_job_user_scope(
    sync_jobs, client, db_session, make_user, make_group, auth_header_for, fake_llm
):
    from backend.project_rag import group_service
    from backend.project_rag.models import Commit
    from backend.models import QueryConversationTurn

    owner, group = _team(db_session, make_user, make_group)
    group.github_repo_url = "https://github.com/example/project"
    db_session.commit()
    repo = group_service.get_or_create_repo(db_session, group)
    db_session.add(
        Commit(
            repo_id=repo.id,
            sha="a" * 40,
            author_name="Ada",
            author_email="ada@example.invalid",
            committed_at=datetime(2026, 10, 1),
            message="Add release notes",
            files_changed=1,
            additions=8,
            deletions=0,
            diff_text="",
        )
    )
    db_session.commit()

    conversation_id = "9dd2a9e6-299a-4dca-93fc-24c78f739c34"
    accepted = client.post(
        f"/groups/{group.id}/query?async=true",
        json={
            "question": "Summarize the release work",
            "sources": ["github"],
            "conversation_id": conversation_id,
        },
        headers=auth_header_for(owner.id),
    )

    assert accepted.status_code == 202
    job = client.get(f"/jobs/{accepted.json()['job_id']}", headers=auth_header_for(owner.id)).json()
    assert job["state"] == "completed" and job["kind"] == "query"
    assert job["result"]["conversation_id"] == conversation_id
    assert job["result"]["sources_used"] == ["github"]
    assert job["result"]["results"]["github"]["stats"]["total_commits"] == 1

    followup = client.post(
        f"/groups/{group.id}/query?async=true",
        json={
            "question": "How many issues are open now?",
            "sources": ["github"],
            "conversation_id": conversation_id,
        },
        headers=auth_header_for(owner.id),
    )
    assert followup.status_code == 202
    followup_job = client.get(
        f"/jobs/{followup.json()['job_id']}", headers=auth_header_for(owner.id)
    ).json()
    assert followup_job["state"] == "completed"
    assert followup_job["result"]["conversation_id"] == conversation_id
    assert len(db_session.query(QueryConversationTurn).filter_by(
        conversation_id=conversation_id, user_id=owner.id, group_id=group.id
    ).all()) == 2
    assert "Previous conversation" in fake_llm.agent_prompts[-1]
    assert "Summarize the release work" in fake_llm.agent_prompts[-1]
    assert "How many issues are open now?" in fake_llm.agent_prompts[-1]


def test_async_report_job_fails_cleanly_when_llm_is_down(
    sync_jobs, client, db_session, make_user, make_group, auth_header_for, monkeypatch, fake_llm
):
    from backend.llm.ollama_client import OllamaError

    fake_llm.error = OllamaError("Ollama is unreachable")
    owner, group = _team(db_session, make_user, make_group)

    accepted = client.post(
        f"/groups/{group.id}/reports/weekly?async=true",
        json={"period_start": "2026-09-07", "period_end": "2026-09-14"}, headers=auth_header_for(owner.id),
    )

    job = client.get(f"/jobs/{accepted.json()['job_id']}", headers=auth_header_for(owner.id)).json()
    assert job["state"] == "failed" and "unreachable" in job["error"]
