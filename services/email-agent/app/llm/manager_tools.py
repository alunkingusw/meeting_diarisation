"""LangChain tool wrappers around the existing manager client.

These are intentionally thin adapters over app.diarisation.client.DiarisationClient so they
can be added incrementally without changing the deterministic pipeline or command handlers.
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from langchain_core.tools import BaseTool, tool

from app.diarisation.client import DiarisationClient


def _serialise(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, list):
        return [_serialise(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialise(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_serialise(item) for item in value]
    return value


def build_manager_tools(client: DiarisationClient) -> list[BaseTool]:
    """Create a LangChain toolset around the existing manager client."""

    @tool
    def list_groups(token: str) -> list[dict[str, Any]]:
        """List the groups the caller can access."""
        return _serialise(client.list_groups(token))

    @tool
    def get_group(token: str, group_id: int) -> dict[str, Any]:
        """Get one group's metadata and members."""
        return _serialise(client.get_group(token, group_id))

    @tool
    def list_meetings(
        token: str,
        group_id: int,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """List meetings in a group, optionally filtered to a date range."""
        from_dt = None if from_date is None else __import__("datetime").date.fromisoformat(from_date)
        to_dt = None if to_date is None else __import__("datetime").date.fromisoformat(to_date)
        return _serialise(client.list_meetings(token, group_id, from_dt, to_dt))

    @tool
    def get_meeting(token: str, group_id: int, meeting_id: int) -> dict[str, Any]:
        """Fetch one meeting's details."""
        return _serialise(client.get_meeting(token, group_id, meeting_id))

    @tool
    def add_comment(token: str, group_id: int, meeting_id: int, comment: str) -> dict[str, Any]:
        """Add a comment to an existing meeting."""
        return _serialise(client.add_comment(token, group_id, meeting_id, comment))

    @tool
    def resolve_aliases(
        token: str,
        group_id: int,
        names: list[str],
        source: str | None = "transcript_name",
    ) -> dict[str, int | None]:
        """Resolve transcript speaker names to group member IDs."""
        return _serialise(client.resolve_aliases(token, group_id, names, source))

    @tool
    def search_transcripts(
        token: str,
        group_id: int,
        query: str,
        meeting_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Search the group's indexed transcripts for semantically relevant text."""
        return _serialise(client.search_transcripts(token, group_id, query, meeting_id))

    @tool
    def login_for_email(email: str) -> str:
        """Exchange a verified email address for a user JWT using the configured service key."""
        return client.login_for_email(email)

    return [
        list_groups,
        get_group,
        list_meetings,
        get_meeting,
        add_comment,
        resolve_aliases,
        search_transcripts,
        login_for_email,
    ]
