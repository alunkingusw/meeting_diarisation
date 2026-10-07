"""
SQLAlchemy ORM models for the Postgres metadata store.

Design note
-----------
This schema is built around *individual contributions over time* rather
than the current state of the codebase:

- `Commit` stores one row per commit, with author + timestamp, so
  "everything Student A did in week 3" is a plain SQL query.
- `Issue` / `IssueComment` / `ReviewComment` mirror that same shape for
  GitHub-side collaboration data (issues and PR review discussion).
- `TrelloAction` mirrors it again for board activity (card comments,
  creations, and moves) - a third, independent source for groups that
  coordinate via Trello rather than (or alongside) GitHub issues.

Each of these tables stores a `chroma_id`: the id of the matching chunk in
Chroma. This is the join key between the two stores - Postgres holds
structured, filterable metadata; Chroma holds the embedding and raw text
for semantic search.

Two conventions worth knowing before changing anything here:

- **All timestamps are timezone-aware** (`DateTime(timezone=True)`, stored
  as UTC). Mixing naive and aware datetimes silently breaks equality
  comparisons, which is how re-ingestion used to duplicate rows.
- **Every table has a natural uniqueness constraint** on the GitHub-side
  identifier, so idempotent re-ingestion is enforced by the database and
  not just by application-level filtering.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base


class Repo(Base):
    """
    Ingest state for one Group's GitHub repo and/or Trello board.

    The Group row owns the URL and board id; this row mirrors them at ingest
    time and carries sync watermarks. Chroma collections are namespaced by
    `namespace`, so groups never share vectors.
    """

    __tablename__ = "rag_repos"

    @property
    def namespace(self) -> str:
        return f"group_{self.group_id}"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # One index record per Group; the Group row stays the source of truth for the repo URL and board id.
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), nullable=False, unique=True)
    github_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    local_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # A Trello board linked to this repo (one board per repo). Ingestion of
    # Trello activity is skipped entirely when this is unset.
    trello_board_id: Mapped[str | None] = mapped_column(String(24), nullable=True)
    # Deliberately separate from `last_synced_at` above, which is stamped
    # once at the end of a run covering commits *and* discussions together
    # (see ingest_service.ingest_repo) and is purely informational. Trello
    # ingestion is incremental - it fetches only actions since this
    # timestamp - so it needs its own watermark that advances only after a
    # successful Trello fetch, independently of the GitHub sub-pipelines.
    trello_last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Tracks a run that may be happening in a background task rather than
    # inline in the request that started it - see app.main:ingest. "idle" is
    # the steady state between runs (including before the first one);
    # "running" from the moment a run starts (inline or backgrounded) until
    # it finishes; "failed" after a run raises, with the error kept alongside
    # so a client polling GET /repos/{id} can see why.
    ingest_status: Mapped[str] = mapped_column(String(16), nullable=False, default="idle")
    ingest_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    commits: Mapped[list["Commit"]] = relationship(back_populates="repo", cascade="all, delete-orphan")
    issues: Mapped[list["Issue"]] = relationship(back_populates="repo", cascade="all, delete-orphan")
    review_comments: Mapped[list["ReviewComment"]] = relationship(
        back_populates="repo", cascade="all, delete-orphan"
    )
    trello_actions: Mapped[list["TrelloAction"]] = relationship(
        back_populates="repo", cascade="all, delete-orphan"
    )


class Commit(Base):
    """One row per git commit - the primary unit for individual-contribution analysis on the code side."""

    __tablename__ = "rag_commits"
    # A sha is unique within a repo, so this both enforces idempotency and
    # gives the "which shas do we already have" lookup an index to use.
    __table_args__ = (UniqueConstraint("repo_id", "sha", name="uq_commits_repo_sha"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("rag_repos.id"), nullable=False, index=True)
    sha: Mapped[str] = mapped_column(String(40), nullable=False)
    author_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    author_email: Mapped[str] = mapped_column(String(256), nullable=False)
    committed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    files_changed: Mapped[int] = mapped_column(Integer, default=0)
    additions: Mapped[int] = mapped_column(Integer, default=0)
    deletions: Mapped[int] = mapped_column(Integer, default=0)
    diff_text: Mapped[str] = mapped_column(Text, nullable=False)

    # Join key into Chroma (see vectorstore.chroma_client.Chunk ids).
    chroma_id: Mapped[str | None] = mapped_column(String(256), nullable=True)

    repo: Mapped["Repo"] = relationship(back_populates="commits")


class Issue(Base):
    """One row per GitHub issue."""

    __tablename__ = "rag_issues"
    __table_args__ = (
        UniqueConstraint("repo_id", "github_issue_number", name="uq_issues_repo_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("rag_repos.id"), nullable=False, index=True)
    github_issue_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    author: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    chroma_id: Mapped[str | None] = mapped_column(String(256), nullable=True)

    repo: Mapped["Repo"] = relationship(back_populates="issues")
    comments: Mapped[list["IssueComment"]] = relationship(
        back_populates="issue", cascade="all, delete-orphan"
    )


class IssueComment(Base):
    """
    One row per comment on a GitHub issue.

    `github_comment_id` is GitHub's own immutable id for the comment. It is
    the dedupe key: timestamps are not unique (two people can comment in
    the same second) and are fragile to compare across timezones.
    """

    __tablename__ = "rag_issue_comments"
    __table_args__ = (
        UniqueConstraint("issue_id", "github_comment_id", name="uq_issue_comments_issue_github_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("rag_issues.id"), nullable=False, index=True)
    github_comment_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    author: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    chroma_id: Mapped[str | None] = mapped_column(String(256), nullable=True)

    issue: Mapped["Issue"] = relationship(back_populates="comments")


class ReviewComment(Base):
    """
    One row per pull-request review comment.

    Kept at the repo level (rather than nested under a PR table) since
    this project does not yet model pull requests as first-class objects -
    `pr_number` is enough to group comments by PR.

    As with IssueComment, `github_comment_id` is the dedupe key.
    """

    __tablename__ = "rag_review_comments"
    __table_args__ = (
        UniqueConstraint("repo_id", "github_comment_id", name="uq_review_comments_repo_github_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("rag_repos.id"), nullable=False, index=True)
    github_comment_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    pr_number: Mapped[int] = mapped_column(Integer, nullable=False)
    author: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    chroma_id: Mapped[str | None] = mapped_column(String(256), nullable=True)

    repo: Mapped["Repo"] = relationship(back_populates="review_comments")


class TrelloAction(Base):
    """
    One row per Trello "Action" (a card comment, card creation, or card
    move) - Trello's own unified event shape, unlike GitHub which exposes
    issues and comments as separate resources. Only these three action
    types are ingested; see app.ingestion.trello_api for the full list of
    types Trello returns and why the rest are filtered out at fetch time.

    `trello_action_id` is Trello's own immutable id, globally unique across
    all of Trello (not just this board) - same idempotency approach as
    IssueComment.github_comment_id.
    """

    __tablename__ = "rag_trello_actions"
    __table_args__ = (
        UniqueConstraint("repo_id", "trello_action_id", name="uq_trello_actions_repo_trello_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("rag_repos.id"), nullable=False, index=True)
    trello_action_id: Mapped[str] = mapped_column(String(24), nullable=False)
    action_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    card_id: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    card_name: Mapped[str] = mapped_column(Text, nullable=False)
    member_creator: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    # The comment body for commentCard, or a synthesized sentence describing
    # the create/move for createCard/updateCard - see trello_chunker.py.
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    chroma_id: Mapped[str | None] = mapped_column(String(256), nullable=True)

    repo: Mapped["Repo"] = relationship(back_populates="trello_actions")
