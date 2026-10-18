"""
Extracts commit history from a local git clone.

No LLM or embedding model is involved here - this is pure git metadata
extraction via GitPython, which itself wraps plain `git log`/`git diff`
commands. Each commit becomes one structured record; chunking (turning
this into embeddable text) happens later in app/chunking/commit_chunker.py.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import git


@dataclass
class ParsedCommit:
    """
    Structured representation of a single commit.

    `diff_text` is the unified diff for the commit (patch format), used
    later as the raw material for the semantic chunk. Kept separate from
    `additions`/`deletions`, which are cheap quantitative signals derived
    from the same diff.

    `committed_at` is always timezone-aware UTC - see parse_commits.
    """

    sha: str
    author_name: str
    author_email: str
    committed_at: datetime
    message: str
    files_changed: int
    additions: int
    deletions: int
    diff_text: str


def parse_commits(repo_path: Path, max_commits: int | None = None) -> list[ParsedCommit]:
    """
    Walk the commit history of a local repo and return structured records.

    Walks **all refs** (`--all`), not just the checked-out branch: work on a
    feature branch that was never merged still counts as a contribution, and
    for group projects that is often where the individual work lives.
    `iter_commits` de-duplicates commits reachable from more than one ref.

    Timestamps come from `committed_datetime`, which is timezone-aware, and
    are normalised to UTC. (The obvious-looking
    `datetime.fromtimestamp(commit.committed_date)` returns *server-local*
    time, which silently shifts every commit by the host's UTC offset and
    corrupts any week-by-week analysis.)

    Parameters
    ----------
    repo_path:
        Path to the local clone (as returned by git_operations.clone_or_pull).
    max_commits:
        Optional cap on how many commits to parse (most recent first).
        Useful for keeping a run fast on a repo with a long history.
    """
    repo = git.Repo(repo_path)
    commits: list[ParsedCommit] = []

    for commit in repo.iter_commits("--all", max_count=max_commits):
        # `commit.stats.total` gives aggregate additions/deletions/files
        # without needing to manually walk the diff ourselves.
        stats = commit.stats.total

        # Unified diff against the commit's first parent. Merge commits are
        # diffed against their first parent only, so a merge shows the net
        # effect of the branch being merged in rather than every commit twice.
        # The initial commit has no parent, so fall back to `git show`.
        try:
            if commit.parents:
                diff_text = repo.git.diff(commit.parents[0].hexsha, commit.hexsha)
            else:
                diff_text = repo.git.show(commit.hexsha, format="", stat=False)
        except git.GitCommandError:
            # A single unreadable diff (e.g. a corrupted object) should not
            # abort ingestion of the whole repo - keep the commit metadata.
            diff_text = ""

        # GitPython decodes the raw git output with errors="surrogateescape"
        # (git/compat.py:safe_decode), so a non-UTF-8 byte in a diff (e.g. a
        # stray Latin-1 "£") survives as an unpaired surrogate codepoint.
        # That's invisible until something re-encodes the string as strict
        # UTF-8 later (Postgres write, embedding call), where it raises
        # UnicodeEncodeError. Scrub it here, at the source, before it
        # propagates anywhere else.
        diff_text = diff_text.encode("utf-8", "replace").decode("utf-8")

        commits.append(
            ParsedCommit(
                sha=commit.hexsha,
                author_name=commit.author.name or "unknown",
                author_email=commit.author.email or "unknown",
                committed_at=commit.committed_datetime.astimezone(timezone.utc),
                message=commit.message.strip() if isinstance(commit.message, str) else "",
                files_changed=stats.get("files", 0),
                additions=stats.get("insertions", 0),
                deletions=stats.get("deletions", 0),
                diff_text=diff_text,
            )
        )

    return commits
