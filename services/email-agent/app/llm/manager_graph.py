"""Minimal LangGraph wrapper for manager operations.

This is intentionally narrow: one graph node executes a selected manager tool with the provided
arguments, then returns the serialized result and a lightweight audit trail. The deterministic
email pipeline remains the source of truth for runtime behavior until the graph is proven on the
same corpus.
"""
from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.diarisation.client import DiarisationClient
from app.llm.manager_tools import build_manager_tools


class ManagerGraphState(TypedDict, total=False):
    token: str
    tool_name: str
    arguments: dict[str, Any]
    result: Any
    audit_events: list[dict[str, Any]]


def _execute_tool(state: ManagerGraphState, tools_by_name: dict[str, Any]) -> ManagerGraphState:
    tool_name = state.get("tool_name")
    if not tool_name:
        raise ValueError("tool_name is required")
    tool = tools_by_name.get(tool_name)
    if tool is None:
        raise ValueError(f"Unsupported tool: {tool_name}")
    payload = state.get("arguments", {}) or {}
    audit = state.get("audit_events", [])
    audit.append({"event": "tool_start", "tool_name": tool_name, "arguments": payload})
    result = tool.invoke(payload)
    audit.append({"event": "tool_result", "tool_name": tool_name, "result": result})
    return {**state, "result": result, "audit_events": audit}


def build_manager_graph(client: DiarisationClient):
    tools = build_manager_tools(client)
    tools_by_name = {tool.name: tool for tool in tools}

    builder = StateGraph(ManagerGraphState)
    builder.add_node("execute_manager_tool", lambda state: _execute_tool(state, tools_by_name))
    builder.add_edge(START, "execute_manager_tool")
    builder.add_edge("execute_manager_tool", END)
    return builder.compile()
