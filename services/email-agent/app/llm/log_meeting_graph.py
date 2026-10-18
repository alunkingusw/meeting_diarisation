"""Deterministic LangGraph workflow for transcript-free meeting notes."""
from __future__ import annotations

from datetime import datetime
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.diarisation.client import DiarisationClient
from app.diarisation.group_matching import Matched, group_clarification_question, match_group


class LogMeetingGraphState(TypedDict, total=False):
    job_id: str
    sender_email: str
    group_hint: str | None
    meeting_date: str
    comment_text: str
    token: str
    groups: list[Any]
    group_id: int | None
    group_name: str | None
    meeting_id: int | None
    comment_id: int | None
    clarification_question: str | None
    clarification_expected_field: str | None
    clarification_options: list[str]
    execution_error: str | None
    audit_events: list[dict[str, Any]]


def _audit(state: LogMeetingGraphState, event: str, **metadata: Any) -> list[dict[str, Any]]:
    events = state.setdefault("audit_events", [])
    events.append({"event": event, **metadata})
    return events


def _login_for_email(
    state: LogMeetingGraphState, client: DiarisationClient
) -> LogMeetingGraphState:
    _audit(state, "login_start", sender_email=state["sender_email"])
    token = client.login_for_email(state["sender_email"])
    _audit(state, "login_result")
    return {**state, "token": token, "audit_events": state["audit_events"]}


def _list_groups(
    state: LogMeetingGraphState, client: DiarisationClient
) -> LogMeetingGraphState:
    groups = client.list_groups(state["token"])
    _audit(state, "groups_listed", count=len(groups))
    return {**state, "groups": groups, "audit_events": state["audit_events"]}


def _resolve_group(state: LogMeetingGraphState) -> LogMeetingGraphState:
    groups = state.get("groups", [])
    match = match_group(state.get("group_hint"), groups)
    if isinstance(match, Matched):
        _audit(state, "group_matched", group_id=match.group.id, group_name=match.group.name)
        return {
            **state,
            "group_id": match.group.id,
            "group_name": match.group.name,
            "audit_events": state["audit_events"],
        }

    question = group_clarification_question(match, groups, "this meeting")
    _audit(state, "clarification_required", question=question)
    return {
        **state,
        "group_id": None,
        "group_name": None,
        "meeting_id": None,
        "clarification_question": question,
        "clarification_expected_field": "group_hint",
        "clarification_options": [group.name for group in groups],
        "audit_events": state["audit_events"],
    }


def _route_after_group_resolution(state: LogMeetingGraphState) -> str:
    return END if state.get("clarification_question") else "create_meeting"


def _create_meeting(
    state: LogMeetingGraphState, client: DiarisationClient
) -> LogMeetingGraphState:
    meeting = client.create_meeting(
        state["token"],
        state["group_id"],
        datetime.fromisoformat(state["meeting_date"]),
        idempotency_key=state["job_id"],
    )
    _audit(state, "meeting_created", meeting_id=meeting.id)
    return {**state, "meeting_id": meeting.id, "audit_events": state["audit_events"]}


def _save_notes(
    state: LogMeetingGraphState, client: DiarisationClient
) -> LogMeetingGraphState:
    try:
        comment = client.add_comment(
            state["token"], state["group_id"], state["meeting_id"], state["comment_text"]
        )
    except Exception as exc:
        _audit(state, "meeting_notes_failed", reason=str(exc))
        return {**state, "execution_error": str(exc), "audit_events": state["audit_events"]}
    _audit(state, "meeting_notes_saved", comment_id=comment.id)
    return {**state, "comment_id": comment.id, "audit_events": state["audit_events"]}


def build_log_meeting_graph(client: DiarisationClient):
    builder = StateGraph(LogMeetingGraphState)
    builder.add_node("login_for_email", lambda state: _login_for_email(state, client))
    builder.add_node("list_groups", lambda state: _list_groups(state, client))
    builder.add_node("resolve_group", _resolve_group)
    builder.add_node("create_meeting", lambda state: _create_meeting(state, client))
    builder.add_node("save_notes", lambda state: _save_notes(state, client))
    builder.add_edge(START, "login_for_email")
    builder.add_edge("login_for_email", "list_groups")
    builder.add_edge("list_groups", "resolve_group")
    builder.add_conditional_edges(
        "resolve_group",
        _route_after_group_resolution,
        {"create_meeting": "create_meeting", END: END},
    )
    builder.add_edge("create_meeting", "save_notes")
    builder.add_edge("save_notes", END)
    return builder.compile()