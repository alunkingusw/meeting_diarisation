"""Minimal LangGraph workflow for a single add-comment command.

This intentionally mirrors the existing deterministic handler logic for add_comment:
1. exchange the verified sender email for a JWT via login_for_email
2. call add_comment against the backend meeting

The existing pipeline remains the default execution path until parity is proven.
"""
from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.diarisation.client import DiarisationClient


class AddCommentGraphState(TypedDict, total=False):
    sender_email: str
    group_id: int
    meeting_id: int
    comment: str
    token: str
    result: Any
    audit_events: list[dict[str, Any]]


def _login_for_email(state: AddCommentGraphState, client: DiarisationClient) -> AddCommentGraphState:
    audit = state.setdefault("audit_events", [])
    email = state["sender_email"]
    audit.append({"event": "login_start", "sender_email": email})
    token = client.login_for_email(email)
    audit.append({"event": "login_result", "sender_email": email, "token_prefix": token[:8]})
    return {**state, "token": token, "audit_events": audit}


def _add_comment(state: AddCommentGraphState, client: DiarisationClient) -> AddCommentGraphState:
    audit = state.setdefault("audit_events", [])
    group_id = state["group_id"]
    meeting_id = state["meeting_id"]
    comment = state["comment"]
    token = state["token"]
    audit.append({"event": "add_comment_start", "group_id": group_id, "meeting_id": meeting_id})
    result = client.add_comment(token, group_id, meeting_id, comment)
    audit.append({"event": "add_comment_result", "group_id": group_id, "meeting_id": meeting_id, "result": result})
    return {**state, "result": result, "audit_events": audit}


def build_add_comment_graph(client: DiarisationClient):
    builder = StateGraph(AddCommentGraphState)
    builder.add_node("login_for_email", lambda state: _login_for_email(state, client))
    builder.add_node("add_comment", lambda state: _add_comment(state, client))
    builder.add_edge(START, "login_for_email")
    builder.add_edge("login_for_email", "add_comment")
    builder.add_edge("add_comment", END)
    return builder.compile()
