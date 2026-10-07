"""
Computed facts about a project, straight from Postgres.

Why this exists
---------------
Semantic search alone answers "what work was done on authentication?" well,
and answers "how many commits did each person make?" badly - it returns the
k most similar chunks, which is a *sample*, and an LLM handed a sample will
happily state a total. Counting, coverage and "who has gone quiet" questions
need aggregates over every row, which is exactly what SQL is for.

So the query pipeline sends the LLM both: retrieved excerpts for the
qualitative part of a question, and the figures below for the quantitative
part. Every number the model reports should come from here.
"""

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import DateTime, func, select
from sqlalchemy.orm import Session

from backend.project_rag.models import Commit, Issue, IssueComment, Repo, ReviewComment, TrelloAction


@dataclass
class ContributorStats:
    """Per-person activity totals for one repo."""

    name: str
    commits: int = 0
    additions: int = 0
    deletions: int = 0
    first_commit_at: datetime | None = None
    last_commit_at: datetime | None = None
    issues_opened: int = 0
    issue_comments: int = 0
    review_comments: int = 0
    trello_actions: int = 0

    @property
    def total_activity(self) -> int:
        return (
            self.commits + self.issues_opened + self.issue_comments
            + self.review_comments + self.trello_actions
        )


@dataclass
class WeeklyActivity:
    """Commit counts bucketed by ISO week, oldest first."""

    week_starting: datetime
    commits: int
    authors: int


@dataclass
class ProjectStats:
    """Everything computed about one repo, ready to render into a prompt."""

    repo_id: int
    repo_name: str
    total_commits: int = 0
    total_issues: int = 0
    open_issues: int = 0
    closed_issues: int = 0
    total_issue_comments: int = 0
    total_review_comments: int = 0
    total_trello_actions: int = 0
    first_activity_at: datetime | None = None
    last_activity_at: datetime | None = None
    contributors: list[ContributorStats] = field(default_factory=list)
    weekly_activity: list[WeeklyActivity] = field(default_factory=list)
    last_synced_at: datetime | None = None

    @property
    def is_empty(self) -> bool:
        return (
            self.total_commits == 0
            and self.total_issues == 0
            and self.total_trello_actions == 0
        )


SOURCES = ("github", "trello")


def collect_project_stats(
    db: Session,
    repo: Repo,
    since: datetime | None = None,
    weeks: int = 12,
    sources: tuple[str, ...] = SOURCES,
    label: str | None = None,
) -> ProjectStats:
    """
    Aggregate all activity for one repo into a `ProjectStats`.

    Runs a handful of GROUP BY queries rather than loading rows into Python:
    the point is to be correct over the *whole* dataset, cheaply, however
    large it is.

    `since`, if given, restricts every count to activity on or after that
    date - so the facts given to the LLM stay consistent with a retrieval
    window like "what happened last week" instead of always reporting
    all-time totals.
    """
    stats = ProjectStats(
        repo_id=repo.id, repo_name=label or repo.name, last_synced_at=repo.last_synced_at
    )

    contributors: dict[str, ContributorStats] = {}

    def contributor(name: str) -> ContributorStats:
        return contributors.setdefault(name, ContributorStats(name=name))

    def since_filter(column):
        return (column >= since,) if since else ()

    commit_since = since_filter(Commit.committed_at)
    use_github = "github" in sources
    use_trello = "trello" in sources

    # --- Commits, grouped by git author name ---
    commit_rows = [] if not use_github else db.execute(
        select(
            Commit.author_name,
            func.count(Commit.id),
            func.coalesce(func.sum(Commit.additions), 0),
            func.coalesce(func.sum(Commit.deletions), 0),
            func.min(Commit.committed_at),
            func.max(Commit.committed_at),
        )
        .where(Commit.repo_id == repo.id, *commit_since)
        .group_by(Commit.author_name)
    ).all()

    for name, count, additions, deletions, first_at, last_at in commit_rows:
        entry = contributor(name)
        entry.commits = count
        entry.additions = int(additions)
        entry.deletions = int(deletions)
        entry.first_commit_at = first_at
        entry.last_commit_at = last_at
        stats.total_commits += count

    # --- Issues, grouped by GitHub author login ---
    issue_rows = [] if not use_github else db.execute(
        select(Issue.author, Issue.state, func.count(Issue.id))
        .where(Issue.repo_id == repo.id, *since_filter(Issue.created_at))
        .group_by(Issue.author, Issue.state)
    ).all()

    for name, state, count in issue_rows:
        contributor(name).issues_opened += count
        stats.total_issues += count
        if state == "open":
            stats.open_issues += count
        else:
            stats.closed_issues += count

    # --- Issue comments (joined through issues to scope by repo) ---
    comment_rows = [] if not use_github else db.execute(
        select(IssueComment.author, func.count(IssueComment.id))
        .join(Issue, IssueComment.issue_id == Issue.id)
        .where(Issue.repo_id == repo.id, *since_filter(IssueComment.created_at))
        .group_by(IssueComment.author)
    ).all()

    for name, count in comment_rows:
        contributor(name).issue_comments = count
        stats.total_issue_comments += count

    # --- PR review comments ---
    review_rows = [] if not use_github else db.execute(
        select(ReviewComment.author, func.count(ReviewComment.id))
        .where(ReviewComment.repo_id == repo.id, *since_filter(ReviewComment.created_at))
        .group_by(ReviewComment.author)
    ).all()

    for name, count in review_rows:
        contributor(name).review_comments = count
        stats.total_review_comments += count

    # --- Trello board activity (only present when the repo has a linked board) ---
    trello_rows = [] if not use_trello else db.execute(
        select(TrelloAction.member_creator, func.count(TrelloAction.id))
        .where(TrelloAction.repo_id == repo.id, *since_filter(TrelloAction.created_at))
        .group_by(TrelloAction.member_creator)
    ).all()

    for name, count in trello_rows:
        contributor(name).trello_actions = count
        stats.total_trello_actions += count

    # --- Overall activity window, across every record type in scope ---
    ranges = []
    if use_github:
        ranges.append(
            db.execute(
                select(func.min(Commit.committed_at), func.max(Commit.committed_at)).where(
                    Commit.repo_id == repo.id, *commit_since
                )
            ).one()
        )
        ranges.append(
            db.execute(
                select(func.min(Issue.created_at), func.max(Issue.created_at)).where(
                    Issue.repo_id == repo.id, *since_filter(Issue.created_at)
                )
            ).one()
        )
        ranges.append(
            db.execute(
                select(func.min(IssueComment.created_at), func.max(IssueComment.created_at))
                .join(Issue, IssueComment.issue_id == Issue.id)
                .where(Issue.repo_id == repo.id, *since_filter(IssueComment.created_at))
            ).one()
        )
        ranges.append(
            db.execute(
                select(func.min(ReviewComment.created_at), func.max(ReviewComment.created_at)).where(
                    ReviewComment.repo_id == repo.id, *since_filter(ReviewComment.created_at)
                )
            ).one()
        )
    if use_trello:
        ranges.append(
            db.execute(
                select(func.min(TrelloAction.created_at), func.max(TrelloAction.created_at)).where(
                    TrelloAction.repo_id == repo.id, *since_filter(TrelloAction.created_at)
                )
            ).one()
        )
    firsts = [first for first, _ in ranges if first is not None]
    lasts = [last for _, last in ranges if last is not None]
    stats.first_activity_at = min(firsts) if firsts else None
    stats.last_activity_at = max(lasts) if lasts else None

    # --- Commits per week, most recent `weeks` buckets ---
    # `type_` is given explicitly so SQLAlchemy knows to hand back a datetime
    # rather than an untyped value from whatever the database returns.
    week_bucket = func.date_trunc("week", Commit.committed_at, type_=DateTime(timezone=True))
    week_rows = [] if not use_github else db.execute(
        select(week_bucket, func.count(Commit.id), func.count(func.distinct(Commit.author_name)))
        .where(Commit.repo_id == repo.id, *commit_since)
        .group_by(week_bucket)
        .order_by(week_bucket.desc())
        .limit(weeks)
    ).all()

    stats.weekly_activity = [
        WeeklyActivity(week_starting=week, commits=count, authors=authors)
        for week, count, authors in reversed(week_rows)
    ]

    stats.contributors = sorted(
        contributors.values(), key=lambda c: c.total_activity, reverse=True
    )
    return stats


def _fmt_date(value: datetime | None) -> str:
    return value.date().isoformat() if value else "n/a"


def format_stats_for_prompt(stats: ProjectStats, sources: tuple[str, ...] = SOURCES) -> str:
    """
    Render `ProjectStats` as compact text for the LLM prompt.

    Plain text rather than JSON: it costs fewer tokens and small local models
    follow a labelled table more reliably than nested objects.
    """
    if stats.is_empty:
        return "No ingested activity found for this repo."

    use_github = "github" in sources
    use_trello = "trello" in sources
    totals = []
    if use_github:
        totals.append(
            f"{stats.total_commits} commits, {stats.total_issues} issues "
            f"({stats.open_issues} open / {stats.closed_issues} closed), "
            f"{stats.total_issue_comments} issue comments, "
            f"{stats.total_review_comments} PR review comments"
        )
    if use_trello:
        totals.append(f"{stats.total_trello_actions} Trello card actions")

    lines = [
        f"Project: {stats.repo_name}",
        f"Activity window: {_fmt_date(stats.first_activity_at)} to {_fmt_date(stats.last_activity_at)}",
        f"Last ingested: {_fmt_date(stats.last_synced_at)}",
        f"Totals: {', '.join(totals)}",
        "",
        "Per-contributor totals (complete, not a sample):",
    ]

    for contrib in stats.contributors:
        parts = []
        if use_github:
            parts.append(
                f"{contrib.commits} commits (+{contrib.additions}/-{contrib.deletions}), "
                f"{contrib.issues_opened} issues opened, "
                f"{contrib.issue_comments} issue comments, "
                f"{contrib.review_comments} review comments"
            )
        if use_trello:
            parts.append(f"{contrib.trello_actions} Trello card actions")
        active = (
            f", active {_fmt_date(contrib.first_commit_at)} to {_fmt_date(contrib.last_commit_at)}"
            if use_github and contrib.commits
            else ""
        )
        lines.append(f"- {contrib.name}: {', '.join(parts)}{active}")

    if stats.weekly_activity:
        lines += ["", "Commits per week (week starting -> commits by N authors):"]
        for week in stats.weekly_activity:
            lines.append(
                f"- {_fmt_date(week.week_starting)} -> {week.commits} commits, "
                f"{week.authors} author(s)"
            )

    lines += [
        "",
        "Note: commit names come from git author config, issue/comment names "
        "are GitHub logins, and Trello card action names are Trello display "
        "names. The same person may appear under different names in each.",
    ]
    return "\n".join(lines)
