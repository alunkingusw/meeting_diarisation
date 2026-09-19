"""Dispatch graph-backed command execution for the manager client.

This is intentionally narrow: it exposes graph execution for the command shapes the email agent
already models, while leaving the deterministic pipeline as the default runtime mechanism until
we validate parity on a real fixture set.
"""
from __future__ import annotations

from app.diarisation.client import DiarisationClient
from app.llm.comment_graph import build_add_comment_graph


class CommandGraphDispatcher:
    def __init__(self, diarisation_client: DiarisationClient):
        self._client = diarisation_client
        self._add_comment_graph = build_add_comment_graph(diarisation_client)

    def execute_add_comment(self, sender_email: str, group_id: int, meeting_id: int, comment: str):
        return self._add_comment_graph.invoke(
            {
                "sender_email": sender_email,
                "group_id": group_id,
                "meeting_id": meeting_id,
                "comment": comment,
            }
        )
