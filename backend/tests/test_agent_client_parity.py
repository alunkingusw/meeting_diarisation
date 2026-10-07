"""Runs the email agent's real DiarisationClient against a live backend, one call per agent action.

This is the parity check between the email channel and the API: everything the agent can do goes
through a route a Postman user can call too, using the emailing user's own token.
"""
import socket
import sys
import threading
import time
from datetime import date, datetime
from pathlib import Path

import httpx
import pytest

AGENT_DIR = Path(__file__).resolve().parents[2] / "services" / "email-agent"
VTT = b"WEBVTT\n\n00:00:01.000 --> 00:00:09.000\n<v Bob>We agreed to ship the API.</v>\n"
SERVICE_KEY = "parity-service-key"


class FakeLLM:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def chat(self, system_prompt, user_prompt):
        from backend.llm.ollama_client import LLMAnswer

        return LLMAnswer(text="fake answer", model="fake-model", prompt_eval_count=None, eval_count=None)


@pytest.fixture
def live_backend(app, db_session, monkeypatch):
    import uvicorn

    monkeypatch.setattr("backend.auth.SERVICE_API_KEY", SERVICE_KEY)
    monkeypatch.setattr("backend.transcript_rag.indexer.index_transcript", lambda **kwargs: {})
    monkeypatch.setattr("backend.summarization.summariser.summarise_meeting_task", lambda *a, **k: None)

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def agent_client(live_backend):
    sys.path.insert(0, str(AGENT_DIR))
    from app.diarisation.client import DiarisationClient

    client = DiarisationClient(live_backend, 10.0, 1, 0.1, SERVICE_KEY, 30.0)
    yield client
    client.close()
    sys.path.remove(str(AGENT_DIR))


def _team(db_session, make_user, make_group, make_member):
    owner = make_user(username="alice")
    owner.email = "alice@uni.ac.uk"
    group = make_group(name="Team A", owner=owner)
    bob = make_member(name="Bob", group=group)
    db_session.commit()
    return owner, group, bob


def test_agent_actions_run_against_real_routes(
    agent_client, db_session, make_user, make_group, make_member, monkeypatch
):
    from backend.models import Meeting

    owner, group, bob = _team(db_session, make_user, make_group, make_member)
    group_service = __import__("backend.project_rag.group_service", fromlist=["x"])
    chunk = {
        "chunk_id": "1_00000", "meeting_id": "1", "meeting_title": "Team A", "meeting_date": "2026-10-01",
        "speaker": "Bob", "text": "We agreed to ship the API.", "start_ts": "00:00:01.000", "end_ts": "00:00:09.000",
    }
    monkeypatch.setattr(group_service, "OllamaClient", FakeLLM)
    monkeypatch.setattr(group_service, "search_transcripts", lambda *a, **k: [chunk])
    monkeypatch.setattr(group_service, "transcripts_in_window", lambda *a, **k: [chunk])
    monkeypatch.setattr("backend.engine.report_graph.OllamaClient", FakeLLM)

    # submit_transcript / log_meeting / add_comment path
    token = agent_client.login_for_email("Alice@uni.ac.uk")
    assert [g.name for g in agent_client.list_groups(token)] == ["Team A"]
    assert [m.name for m in agent_client.get_group(token, group.id).members] == ["Bob"]
    meeting = agent_client.create_meeting(token, group.id, datetime(2026, 10, 1, 10), "parity-key-1")
    assert agent_client.create_meeting(token, group.id, datetime(2026, 10, 1, 10), "parity-key-1").id == meeting.id
    uploaded = agent_client.upload_file(token, group.id, meeting.id, "meeting.vtt", VTT)
    assert uploaded.type.lower().endswith("transcript_provided")
    assert agent_client.resolve_aliases(token, group.id, ["bob", "Zed"]) == {"bob": bob.id, "Zed": None}
    assert agent_client.add_attendee(token, group.id, meeting.id, bob.id).name == "Bob"
    comment = agent_client.add_comment(token, group.id, meeting.id, "Update the docs")
    assert comment.comment == "Update the docs" and comment.user_id == owner.id
    assert [m.id for m in agent_client.list_meetings(token, group.id)] == [meeting.id]
    assert agent_client.get_meeting(token, group.id, meeting.id).id == meeting.id

    # assess_query path
    assert agent_client.query_source(token, group.id, "conversation", "What was agreed?").answer == "fake answer"
    unified = agent_client.query_unified(token, group.id, "What was agreed?", sources=["conversation"])
    assert unified.sources_used == ["conversation"]
    assert agent_client.search_transcripts(token, group.id, "ship")[0].speaker == "Bob"

    # job status / cancel path: a query run as a backend job, then looked up by the agent's client
    seen = []
    assert agent_client.query_source(token, group.id, "conversation", "Again?", on_job=seen.append).answer == "fake answer"
    job = agent_client.get_job(token, seen[0])
    assert job.state == "completed" and job.kind == "query"
    assert [j.id for j in agent_client.list_jobs(token, kind="query")] == [seen[0]]
    from app.diarisation.client import ConflictError

    with pytest.raises(ConflictError):
        agent_client.cancel_job(token, seen[0])

    # weekly report path
    stored = db_session.get(Meeting, meeting.id)
    stored.summary = "The team agreed to ship the API."
    db_session.commit()
    report = agent_client.compose_weekly_report(token, group.id, date(2026, 9, 30), date(2026, 10, 7))
    assert report.report_text == "fake answer"
    assert {e.evidence_id for e in report.evidence} >= {f"meeting-{meeting.id}-summary", f"meeting-{meeting.id}-comments"}
    answer = agent_client.answer_report_question(
        token, group.id, "What was agreed?", report.evidence, date(2026, 9, 30), date(2026, 10, 7)
    )
    assert answer == "fake answer"
    window = agent_client.transcript_chunks_in_window(token, group.id, date(2026, 9, 30), date(2026, 10, 7))
    assert window[0].speaker == "Bob"


def test_email_token_is_the_users_own_not_a_service_identity(
    agent_client, live_backend, db_session, make_user, make_group, make_member
):
    _team(db_session, make_user, make_group, make_member)
    token = agent_client.login_for_email("alice@uni.ac.uk")
    headers = {"Authorization": f"Bearer {token}"}

    # The minted token carries no service privileges...
    assert httpx.post(f"{live_backend}/admin/user-token", json={"email": "x@y.z"}, headers=headers).status_code == 401
    assert httpx.get(f"{live_backend}/admin/group-owners", headers=headers).status_code == 401
    # ...and a non-admin user's token cannot reach administrator routes.
    assert httpx.get(f"{live_backend}/users/", headers=headers).status_code == 403
    assert httpx.get(f"{live_backend}/users/me", headers=headers).json()["username"] == "alice"


def test_group_member_email_token_is_limited_to_member_actions(
    agent_client, db_session, make_user, make_group, make_member
):
    from app.diarisation.client import AuthError

    owner, group, bob = _team(db_session, make_user, make_group, make_member)
    bob.email = "bob@uni.ac.uk"
    meeting = __import__("backend.models", fromlist=["Meeting"]).Meeting(group_id=group.id, date=datetime(2026, 10, 1))
    db_session.add(meeting)
    db_session.commit()

    token = agent_client.login_for_email("bob@uni.ac.uk")

    assert agent_client.add_comment(token, group.id, meeting.id, "From Bob").group_member_id == bob.id
    with pytest.raises(AuthError):
        agent_client.query_source(token, group.id, "conversation", "anything")


def test_admin_over_email_has_no_admin_rights(
    agent_client, live_backend, db_session, make_user, make_group, make_member, auth_header_for
):
    from app.diarisation.client import AuthError

    admin = make_user(username="root", is_admin=True)
    admin.email = "root@uni.ac.uk"
    other = make_user(username="bob")
    foreign = make_group(name="Not Roots", owner=other)
    own = make_group(name="Roots Group", owner=admin)
    db_session.commit()

    token = agent_client.login_for_email("root@uni.ac.uk")
    email_headers = {"Authorization": f"Bearer {token}"}
    api_headers = auth_header_for(admin.id)

    # Admin routes and overrides are refused over email, with an explanatory detail...
    denied = httpx.get(f"{live_backend}/users/", headers=email_headers)
    assert denied.status_code == 403 and "not available over email" in denied.json()["detail"]
    all_groups = httpx.get(f"{live_backend}/groups/?all_groups=true", headers=email_headers)
    assert all_groups.status_code == 403 and "not available over email" in all_groups.json()["detail"]
    with pytest.raises(AuthError):
        agent_client.query_source(token, foreign.id, "conversation", "anything")
    # ...ordinary access to groups the admin owns still works over email...
    assert [g.name for g in agent_client.list_groups(token)] == ["Roots Group"]
    assert agent_client.get_group(token, own.id).name == "Roots Group"
    # ...and the same admin keeps every admin right through the API.
    assert httpx.get(f"{live_backend}/users/", headers=api_headers).status_code == 200
    assert httpx.get(f"{live_backend}/groups/?all_groups=true", headers=api_headers).status_code == 200
    assert httpx.get(f"{live_backend}/groups/{foreign.id}", headers=api_headers).status_code == 200
