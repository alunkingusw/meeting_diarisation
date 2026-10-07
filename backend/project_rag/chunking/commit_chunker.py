"""
Chunks commit data for embedding.

Chunking unit: one chunk per commit (not per function/class in the final
codebase). This follows from the project's focus on individual
contributions over time rather than the current state of the code - the
commit message plus diff is kept together as one chunk so a semantic
search over "what did this commit do" retrieves the full picture in one hit.
"""

from backend.project_rag.chunking.types import Chunk
from backend.project_rag.ingestion.commit_parser import ParsedCommit

# Diffs on very large commits can be huge; cap the diff text included in
# the embedded chunk to keep embeddings meaningful (embedding models have
# their own token limits), while the full diff is still stored in
# Postgres regardless.
MAX_DIFF_CHARS = 4000


def chunk_commit(commit: ParsedCommit, repo_name: str) -> Chunk:
    """Build a single Chunk from a parsed commit."""
    diff_excerpt = commit.diff_text[:MAX_DIFF_CHARS]
    if len(commit.diff_text) > MAX_DIFF_CHARS:
        diff_excerpt += "\n... [diff truncated for embedding] ..."

    text = (
        f"Commit {commit.sha[:8]} by {commit.author_name} in {repo_name} "
        f"on {commit.committed_at.date().isoformat()}\n"
        f"Message: {commit.message}\n"
        f"Files changed: {commit.files_changed}, "
        f"+{commit.additions}/-{commit.deletions}\n"
        f"Diff:\n{diff_excerpt}"
    )

    return Chunk(
        text=text,
        source_type="commit",
        source_id=commit.sha,
        author=commit.author_name,
        timestamp=commit.committed_at,
        repo_name=repo_name,
        metadata={
            "files_changed": commit.files_changed,
            "additions": commit.additions,
            "deletions": commit.deletions,
        },
    )


def chunk_commits(commits: list[ParsedCommit], repo_name: str) -> list[Chunk]:
    """Convenience wrapper: chunk a whole list of commits."""
    return [chunk_commit(c, repo_name) for c in commits]
