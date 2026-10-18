"""Deterministic LangGraph workflow for submit_transcript.

This mirrors the live submission contract: validate the attachment, resolve a meeting date from
the transcript (or ask for clarification before contacting the backend), resolve the group
deterministically, and only then create the meeting.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.diarisation.client import DiarisationClient
from app.diarisation.group_matching import Matched, group_clarification_question, match_group


class SubmitTranscriptGraphState(TypedDict, total=False):
    job_id: str
    sender_email: str
    attachment_path: str
    attachment_filename: str
    attachment_size_bytes: int
    max_attachment_size_bytes: int
    group_hint: str | None
    token: str
    groups: list[Any]
    group_id: int | None
    group_name: str | None
    meeting_date: str | None
    meeting_date_source: str | None
    meeting_id: int | None
    raw_file_id: int | None
    speakers: list[str]
    resolved_attendees: list[str]
    unresolved_speakers: list[str]
    resolved_member_ids: dict[str, int]
    clarification_question: str | None
    clarification_expected_field: str | None
    clarification_options: list[str]
    audit_events: list[dict[str, Any]]


def _audit(state: SubmitTranscriptGraphState, event: str, **metadata: Any) -> list[dict[str, Any]]:
    events = state.setdefault("audit_events", [])
    events.append({"event": event, **metadata})
    return events


def _validate_trusted_state(state: SubmitTranscriptGraphState) -> SubmitTranscriptGraphState:
    path = Path(state["attachment_path"])
    if path.suffix.lower() != ".vtt":
        raise ValueError("submit_transcript requires a .vtt attachment")
    if not path.is_file():
        raise ValueError("transcript attachment is missing")
    size = path.stat().st_size
    max_size = state.get("max_attachment_size_bytes")
    if max_size is not None and size > max_size:
        raise ValueError("transcript attachment exceeds the configured size limit")
    if state.get("attachment_size_bytes") is not None and size != state["attachment_size_bytes"]:
        raise ValueError("transcript attachment changed after validation")
    _audit(state, "validate_trusted_state", filename=state["attachment_filename"], size_bytes=size)
    return {**state, "attachment_size_bytes": size, "audit_events": state["audit_events"]}


def _resolve_meeting_date(state: SubmitTranscriptGraphState) -> SubmitTranscriptGraphState:
    from app.vtt.parser import VttParseError, parse_vtt

    try:
        parsed_vtt = parse_vtt(state["attachment_path"])
    except VttParseError as exc:
        raise ValueError(str(exc)) from exc

    if parsed_vtt.meeting_date is not None:
        _audit(
            state,
            "meeting_date_resolved",
            source=parsed_vtt.meeting_date_source,
            meeting_date=parsed_vtt.meeting_date.isoformat(),
        )
        return {
            **state,
            "meeting_date": parsed_vtt.meeting_date.isoformat(),
            "meeting_date_source": parsed_vtt.meeting_date_source,
            "speakers": state.get("speakers") or parsed_vtt.speakers,
            "audit_events": state["audit_events"],
        }

    if state.get("meeting_date"):
        _audit(state, "meeting_date_present", meeting_date=state["meeting_date"])
        return {
            **state,
            "speakers": state.get("speakers") or parsed_vtt.speakers,
            "audit_events": state["audit_events"],
        }

    question = (
        "I couldn't find a meeting date in the transcript or your email. What date was "
        "this meeting (e.g. '11 August 2026')?"
    )
    _audit(state, "clarification_required", question=question)
    return {
        **state,
        "meeting_date": None,
        "group_id": None,
        "group_name": None,
        "meeting_id": None,
        "clarification_question": question,
        "clarification_expected_field": "meeting_date",
        "clarification_options": [],
        "speakers": state.get("speakers") or parsed_vtt.speakers,
        "audit_events": state["audit_events"],
    }


def _route_after_meeting_date(state: SubmitTranscriptGraphState) -> str:
    return END if state.get("clarification_question") else "login_for_email"


def _login_for_email(state: SubmitTranscriptGraphState, client: DiarisationClient) -> SubmitTranscriptGraphState:
    _audit(state, "login_start", sender_email=state["sender_email"])
    token = client.login_for_email(state["sender_email"])
    _audit(state, "login_result", token_prefix=token[:8])
    return {**state, "token": token, "audit_events": state["audit_events"]}


def _list_groups(state: SubmitTranscriptGraphState, client: DiarisationClient) -> SubmitTranscriptGraphState:
    groups = client.list_groups(state["token"])
    _audit(state, "groups_listed", count=len(groups))
    return {**state, "groups": groups, "audit_events": state["audit_events"]}


def _resolve_group(state: SubmitTranscriptGraphState) -> SubmitTranscriptGraphState:
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
    question = group_clarification_question(match, groups, "this transcript")
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


def _route_after_group_resolution(state: SubmitTranscriptGraphState) -> str:
    return END if state.get("clarification_question") else "create_meeting"


def _create_meeting(state: SubmitTranscriptGraphState, client: DiarisationClient) -> SubmitTranscriptGraphState:
    if state.get("group_id") is None:
        return state
    _audit(
        state,
        "create_meeting_start",
        group_id=state["group_id"],
        idempotency_key=state["job_id"],
    )
    from datetime import datetime

    meeting = client.create_meeting(
        state["token"],
        state["group_id"],
        datetime.fromisoformat(state["meeting_date"]),
        idempotency_key=state["job_id"],
    )
    _audit(state, "create_meeting_result", meeting_id=meeting.id)
    return {**state, "meeting_id": meeting.id, "audit_events": state["audit_events"]}


def _upload_transcript(
    state: SubmitTranscriptGraphState, client: DiarisationClient
) -> SubmitTranscriptGraphState:
    content = Path(state["attachment_path"]).read_bytes()
    raw_file = client.upload_file(
        state["token"],
        state["group_id"],
        state["meeting_id"],
        state["attachment_filename"],
        content,
    )
    _audit(state, "transcript_uploaded", raw_file_id=raw_file.id)
    return {**state, "raw_file_id": raw_file.id, "audit_events": state["audit_events"]}


def _resolve_attendees(
    state: SubmitTranscriptGraphState, client: DiarisationClient
) -> SubmitTranscriptGraphState:
    speakers = state.get("speakers", [])
    resolved_attendees: list[str] = []
    unresolved_speakers: list[str] = []
    if speakers:
        aliases = client.resolve_aliases(state["token"], state["group_id"], speakers)
        for speaker in speakers:
            if aliases.get(speaker) is None:
                unresolved_speakers.append(speaker)
            else:
                resolved_attendees.append(speaker)
    _audit(
        state,
        "attendees_resolved",
        resolved_count=len(resolved_attendees),
        unresolved_count=len(unresolved_speakers),
    )
    return {
        **state,
        "resolved_attendees": resolved_attendees,
        "unresolved_speakers": unresolved_speakers,
        "resolved_member_ids": {
            speaker: aliases[speaker]
            for speaker in resolved_attendees
        } if speakers else {},
        "audit_events": state["audit_events"],
    }


def _add_attendees(
    state: SubmitTranscriptGraphState, client: DiarisationClient
) -> SubmitTranscriptGraphState:
    member_ids = state.get("resolved_member_ids", {})
    for speaker in state.get("resolved_attendees", []):
        client.add_attendee(
            state["token"], state["group_id"], state["meeting_id"], member_ids[speaker]
        )
    _audit(state, "attendees_added", count=len(member_ids))
    return {**state, "audit_events": state["audit_events"]}


def build_submit_transcript_graph(client: DiarisationClient):
    builder = StateGraph(SubmitTranscriptGraphState)
    builder.add_node("validate_trusted_state", _validate_trusted_state)
    builder.add_node("resolve_meeting_date", _resolve_meeting_date)
    builder.add_node("login_for_email", lambda state: _login_for_email(state, client))
    builder.add_node("list_groups", lambda state: _list_groups(state, client))
    builder.add_node("resolve_group", _resolve_group)
    builder.add_node("create_meeting", lambda state: _create_meeting(state, client))
    builder.add_node("upload_transcript", lambda state: _upload_transcript(state, client))
    builder.add_node("resolve_attendees", lambda state: _resolve_attendees(state, client))
    builder.add_node("add_attendees", lambda state: _add_attendees(state, client))
    builder.add_edge(START, "validate_trusted_state")
    builder.add_edge("validate_trusted_state", "resolve_meeting_date")
    builder.add_conditional_edges(
        "resolve_meeting_date",
        _route_after_meeting_date,
        {"login_for_email": "login_for_email", END: END},
    )
    builder.add_edge("login_for_email", "list_groups")
    builder.add_edge("list_groups", "resolve_group")
    builder.add_conditional_edges(
        "resolve_group",
        _route_after_group_resolution,
        {"create_meeting": "create_meeting", END: END},
    )
    builder.add_edge("create_meeting", "upload_transcript")
    builder.add_edge("upload_transcript", "resolve_attendees")
    builder.add_edge("resolve_attendees", "add_attendees")
    builder.add_edge("add_attendees", END)
    return builder.compile()
