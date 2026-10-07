"""
Chunks Trello board activity data.

Chunking unit: one chunk per action (comment, card creation, or card move),
following commit_chunker.py's 1:1 pattern - there is only one action shape
here (Trello already unifies these events), unlike discussion_chunker.py
which has three genuinely different GitHub resource types to chunk.
"""

from backend.project_rag.chunking.types import Chunk
from backend.project_rag.ingestion.trello_api import RemoteTrelloAction


def chunk_trello_action(action: RemoteTrelloAction, repo_name: str) -> Chunk:
    """Build a single Chunk from a Trello action."""
    text = (
        f"Trello {action.action_type} by {action.member_creator} on card "
        f"'{action.card_name}' in {repo_name} on {action.created_at.date().isoformat()}\n"
        f"{action.text}"
    )

    return Chunk(
        text=text,
        source_type="trello_action",
        source_id=action.trello_action_id,
        author=action.member_creator,
        timestamp=action.created_at,
        repo_name=repo_name,
        metadata={
            "action_type": action.action_type,
            "card_name": action.card_name,
        },
    )


def chunk_trello_actions(actions: list[RemoteTrelloAction], repo_name: str) -> list[Chunk]:
    """Convenience wrapper: chunk a whole list of Trello actions."""
    return [chunk_trello_action(a, repo_name) for a in actions]
