"""
Orchestrates a full ingestion run for one repository:

1. Clone/fetch the repo locally (app.ingestion.git_operations).
2. Parse commit history from the local clone (app.ingestion.commit_parser).
3. Fetch issues + issue comments + PR review comments from the GitHub API
   (app.ingestion.github_api).
4. If the repo has a linked Trello board (`repo.trello_board_id`), fetch
   card comments/creations/moves since the last Trello sync
   (app.ingestion.trello_api) - the one source here that is incremental
   rather than a full re-fetch every run, and entirely skipped otherwise.
5. Insert new Commit / Issue / IssueComment / ReviewComment / TrelloAction
   rows into Postgres, skipping ones already ingested so re-running this is
   idempotent.
6. Chunk each data type (app.chunking) and store embeddings in the
   appropriate Chroma collection (app.vectorstore.chroma_client),
   namespaced by group_name if provided, else by repo name.

Idempotency is keyed on each source's own immutable ids (commit sha, issue
number, comment id, Trello action id) rather than on timestamps, and the
database enforces it with unique constraints as well - see app/db/models.py.

`clone_and_count_commits` + `ingest_repo` is the entry point the FastAPI
route calls - keeping orchestration out of the route function itself makes
it easy to reuse (e.g. from a CLI script), and lets the route decide, from
the commit count, whether to run `ingest_repo` inline or hand it to a
background task (see app.main:ingest) before paying for the expensive part
of the run.
"""

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.project_rag.chunking.commit_chunker import chunk_commits
from backend.project_rag.chunking.discussion_chunker import (
    chunk_issue,
    chunk_issue_comment,
    chunk_review_comment,
)
from backend.project_rag.chunking.trello_chunker import chunk_trello_actions
from backend.project_rag.chunking.types import Chunk
from backend.project_rag.models import Commit, Issue, IssueComment, Repo, ReviewComment, TrelloAction
from backend.project_rag.ingestion.commit_parser import parse_commits
from backend.project_rag.ingestion.git_operations import clone_or_pull, count_commits
from backend.project_rag.ingestion.github_api import GitHubClient
from backend.project_rag.ingestion.trello_api import TrelloClient
from backend.project_rag.schemas import IngestSummary
from backend.project_rag.services.repo_stats import SOURCES
from backend.project_rag.vectorstore import add_chunks, collection_name, delete_repo_chunks


def flush_repo(db: Session, repo: Repo, sources: tuple[str, ...] = SOURCES) -> None:
    """
    Delete every commit, issue, comment, and review comment stored for this
    repo in Postgres, and every chunk embedded for it in Chroma.

    Ingestion is normally idempotent by design (see module docstring) -
    re-running it only adds what is missing, on purpose, so a schema or
    chunking change doesn't force a slow full re-embed of an unchanged repo.
    `flush` is the deliberate escape hatch: it clears this repo's own
    records so the next ingest treats everything as new again, without
    touching other repos - including ones sharing a Chroma collection via
    the same group_name.

    Issues are deleted through the ORM (rather than a bulk DELETE) so the
    `cascade="all, delete-orphan"` on `Issue.comments` removes their
    IssueComment rows too - comments have no repo_id of their own to filter
    by directly.
    """
    if "github" in sources:
        for issue in db.scalars(select(Issue).where(Issue.repo_id == repo.id)).all():
            db.delete(issue)
        for commit in db.scalars(select(Commit).where(Commit.repo_id == repo.id)).all():
            db.delete(commit)
        for review_comment in db.scalars(
            select(ReviewComment).where(ReviewComment.repo_id == repo.id)
        ).all():
            db.delete(review_comment)
    if "trello" in sources:
        for trello_action in db.scalars(
            select(TrelloAction).where(TrelloAction.repo_id == repo.id)
        ).all():
            db.delete(trello_action)
    db.commit()

    namespace = repo.namespace
    if "github" in sources:
        delete_repo_chunks(collection_name(namespace, "commits"), repo.name)
        delete_repo_chunks(collection_name(namespace, "discussions"), repo.name)
        repo.last_synced_at = None
    if "trello" in sources:
        delete_repo_chunks(collection_name(namespace, "trello"), repo.name)
        repo.trello_last_synced_at = None
    db.commit()


def clone_and_count_commits(repo: Repo) -> tuple[Path, int]:
    """
    Clone/fetch the repo and report the size of its history, without paying
    for the per-commit diff/stat parsing a full ingest does.

    The caller (app.main:ingest) uses the count to decide whether to run
    `ingest_repo` inline or hand it to a background task, so this has to be
    cheap even on a repo with a very long history.
    """
    local_path = clone_or_pull(repo.github_url)
    repo.local_path = str(local_path)
    return local_path, count_commits(local_path)


def ingest_repo(
    db: Session,
    repo: Repo,
    local_path: Path | None = None,
    sources: tuple[str, ...] = SOURCES,
) -> IngestSummary:
    """
    Run an ingestion pass for the requested sources and return how many
    records of each type were newly ingested.

    `local_path`, if given, is used as-is instead of cloning again - the
    caller has usually already done so via `clone_and_count_commits` to
    decide whether to run this inline or in the background.
    """
    namespace = repo.namespace
    summary = IngestSummary(group_id=repo.group_id)

    if "github" in sources and repo.github_url:
        if local_path is None:
            local_path = clone_or_pull(repo.github_url)
        repo.local_path = str(local_path)
        db.commit()

        summary.commits_ingested = _ingest_commits(db, repo, local_path, namespace)
        (
            summary.issues_ingested,
            summary.issue_comments_ingested,
            summary.review_comments_ingested,
        ) = _ingest_discussions(db, repo, namespace)
        repo.last_synced_at = datetime.now(timezone.utc)

    if "trello" in sources and repo.trello_board_id:
        summary.trello_actions_ingested = _ingest_trello_actions(db, repo, namespace)
        # Advances only on success, independently of last_synced_at.
        repo.trello_last_synced_at = datetime.now(timezone.utc)

    db.commit()
    return summary


def _ingest_commits(db: Session, repo: Repo, local_path: Path, namespace: str) -> int:
    """Parse, store, and embed any commits not already ingested for this repo."""
    parsed = parse_commits(local_path)

    existing_shas = set(
        db.scalars(select(Commit.sha).where(Commit.repo_id == repo.id)).all()
    )
    new_parsed = [c for c in parsed if c.sha not in existing_shas]
    if not new_parsed:
        return 0

    # Persist structured metadata to Postgres first.
    commit_rows = [
        Commit(
            repo_id=repo.id,
            sha=c.sha,
            author_name=c.author_name,
            author_email=c.author_email,
            committed_at=c.committed_at,
            message=c.message,
            files_changed=c.files_changed,
            additions=c.additions,
            deletions=c.deletions,
            diff_text=c.diff_text,
        )
        for c in new_parsed
    ]
    db.add_all(commit_rows)
    db.commit()

    # Then chunk + embed + store in Chroma, and write back the chroma_id
    # join key so the two stores can be cross-referenced later.
    chunks = chunk_commits(new_parsed, repo_name=repo.name)
    add_chunks(collection_name(namespace, "commits"), chunks)

    for row, chunk in zip(commit_rows, chunks):
        row.chroma_id = chunk.chunk_id
    db.commit()

    return len(new_parsed)


def _ingest_discussions(db: Session, repo: Repo, namespace: str) -> tuple[int, int, int]:
    """
    Fetch, store, and embed issues/issue comments/review comments not already
    ingested.

    All three lists come from repo-wide endpoints, so this costs a handful of
    requests regardless of how many issues the repo has, and comments added to
    *previously ingested* issues are picked up too.
    """
    with GitHubClient() as client:
        remote_issues = client.fetch_issues(repo.github_url)
        remote_issue_comments = client.fetch_issue_comments(repo.github_url)
        remote_review_comments = client.fetch_review_comments(repo.github_url)

    chunks: list[Chunk] = []

    # --- Issues: insert new ones, and refresh state on existing ones ---
    existing_issues = {
        row.github_issue_number: row
        for row in db.scalars(select(Issue).where(Issue.repo_id == repo.id)).all()
    }

    new_issues = [i for i in remote_issues if i.number not in existing_issues]
    issue_rows = [
        Issue(
            repo_id=repo.id,
            github_issue_number=i.number,
            title=i.title,
            body=i.body,
            author=i.author,
            state=i.state,
            created_at=i.created_at,
        )
        for i in new_issues
    ]
    db.add_all(issue_rows)

    # An issue closing is real project progress, and the open/closed counts
    # feed the query layer's facts - so update state on issues already stored
    # and re-embed those chunks (their text names the state).
    for remote in remote_issues:
        existing = existing_issues.get(remote.number)
        if existing is not None and existing.state != remote.state:
            existing.state = remote.state
            chunks.append(chunk_issue(remote, repo_name=repo.name))

    db.commit()

    for row, remote in zip(issue_rows, new_issues):
        chunk = chunk_issue(remote, repo_name=repo.name)
        row.chroma_id = chunk.chunk_id
        chunks.append(chunk)

    # --- Issue comments ---
    # The repo-wide endpoint also returns comments on pull requests (a PR is
    # an issue under the hood), so keep only those belonging to issues we
    # actually store.
    issue_id_by_number = {
        row.github_issue_number: row.id
        for row in db.scalars(select(Issue).where(Issue.repo_id == repo.id)).all()
    }
    existing_comment_ids = set(
        db.scalars(
            select(IssueComment.github_comment_id)
            .join(Issue, IssueComment.issue_id == Issue.id)
            .where(Issue.repo_id == repo.id)
        ).all()
    )
    new_issue_comments = [
        c
        for c in remote_issue_comments
        if c.issue_number in issue_id_by_number
        and c.github_comment_id not in existing_comment_ids
    ]
    comment_rows = [
        IssueComment(
            issue_id=issue_id_by_number[c.issue_number],
            github_comment_id=c.github_comment_id,
            author=c.author,
            body=c.body,
            created_at=c.created_at,
        )
        for c in new_issue_comments
    ]
    db.add_all(comment_rows)

    # --- PR review comments ---
    existing_review_ids = set(
        db.scalars(
            select(ReviewComment.github_comment_id).where(ReviewComment.repo_id == repo.id)
        ).all()
    )
    new_review_comments = [
        rc for rc in remote_review_comments if rc.github_comment_id not in existing_review_ids
    ]
    review_rows = [
        ReviewComment(
            repo_id=repo.id,
            github_comment_id=rc.github_comment_id,
            pr_number=rc.pr_number,
            author=rc.author,
            body=rc.body,
            file_path=rc.file_path,
            line=rc.line,
            created_at=rc.created_at,
        )
        for rc in new_review_comments
    ]
    db.add_all(review_rows)
    db.commit()

    for row, remote_comment in zip(comment_rows, new_issue_comments):
        chunk = chunk_issue_comment(remote_comment, repo_name=repo.name)
        row.chroma_id = chunk.chunk_id
        chunks.append(chunk)

    for row, remote_review in zip(review_rows, new_review_comments):
        chunk = chunk_review_comment(remote_review, repo_name=repo.name)
        row.chroma_id = chunk.chunk_id
        chunks.append(chunk)

    # Chunk + embed everything new in one batch, stored in the "discussions"
    # collection (separate from "commits" - see chroma_client module docstring
    # for the rationale).
    add_chunks(collection_name(namespace, "discussions"), chunks)
    db.commit()

    return len(new_issues), len(new_issue_comments), len(new_review_comments)


def _ingest_trello_actions(db: Session, repo: Repo, namespace: str) -> int:
    """
    Fetch, store, and embed Trello board activity not already ingested.

    Unlike the two GitHub sub-pipelines, this fetch is incremental -
    `TrelloClient.fetch_board_actions` is passed `repo.trello_last_synced_at`
    as `since`, so a re-run only asks Trello for actions newer than the last
    successful Trello sync rather than the whole board history. Dedup
    against Postgres by `trello_action_id` still runs regardless, both as a
    backstop against overlap at the `since` boundary and because it is the
    same idempotency convention every other source in this module follows.
    """
    with TrelloClient() as client:
        remote_actions = client.fetch_board_actions(
            repo.trello_board_id, since=repo.trello_last_synced_at
        )

    existing_ids = set(
        db.scalars(
            select(TrelloAction.trello_action_id).where(TrelloAction.repo_id == repo.id)
        ).all()
    )
    new_actions = [a for a in remote_actions if a.trello_action_id not in existing_ids]
    if not new_actions:
        return 0

    action_rows = [
        TrelloAction(
            repo_id=repo.id,
            trello_action_id=a.trello_action_id,
            action_type=a.action_type,
            card_id=a.card_id,
            card_name=a.card_name,
            member_creator=a.member_creator,
            text=a.text,
            created_at=a.created_at,
        )
        for a in new_actions
    ]
    db.add_all(action_rows)
    db.commit()

    chunks = chunk_trello_actions(new_actions, repo_name=repo.name)
    add_chunks(collection_name(namespace, "trello"), chunks)

    for row, chunk in zip(action_rows, chunks):
        row.chroma_id = chunk.chunk_id
    db.commit()

    return len(new_actions)
