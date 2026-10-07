"""
The query half of the RAG loop: question in, grounded answer out.

Pipeline
--------
1. Compute project facts from Postgres (app.services.repo_stats) - complete
   counts, per-contributor totals, week-by-week activity.
2. Retrieve chunks to answer the question from. Two paths, chosen per
   request (see `answer_question`):
   - `since`-scoped and small enough (COMPLETE_RETRIEVAL_ROW_LIMIT): every
     matching commit/issue/comment/Trello action, read straight from
     Postgres - the right shape for a report, where "everything that
     happened this week" beats a relevance-ranked sample of it.
   - Otherwise: semantically relevant chunks from the repo's Chroma
     collections (commits, discussions, and Trello - see CONTENT_TYPES),
     same as before.
3. Assemble both into one prompt, bounded by MAX_CONTEXT_CHARS.
4. Ask the local Ollama model to answer using only that material.
5. Return the answer alongside the sources it was given, so any claim can
   be checked against the underlying commit or comment.

Why both halves: retrieval supplies the qualitative detail ("what was
actually worked on"), the SQL facts supply the quantitative truth ("how
much, by whom, when"). Given only retrieved excerpts, a model asked "how
many commits did Alice make?" will confidently answer from the handful of
chunks it can see. See app/services/repo_stats.py for the longer note.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.project_rag.chunking.commit_chunker import chunk_commit
from backend.project_rag.chunking.discussion_chunker import chunk_issue, chunk_issue_comment, chunk_review_comment
from backend.project_rag.chunking.trello_chunker import chunk_trello_action
from backend.config import settings
from backend.project_rag.models import Commit, Issue, IssueComment, Repo, ReviewComment, TrelloAction
from backend.project_rag.ingestion.commit_parser import ParsedCommit
from backend.project_rag.ingestion.github_api import RemoteIssue, RemoteIssueComment, RemoteReviewComment
from backend.project_rag.ingestion.trello_api import RemoteTrelloAction
from backend.llm.ollama_client import OllamaClient
from backend.project_rag.services.repo_stats import (
    SOURCES, ProjectStats, collect_project_stats, format_stats_for_prompt,
)
from backend.project_rag.vectorstore import RetrievedChunk, collection_name, search

SOURCE_CONTENT_TYPES = {"github": ("commits", "discussions"), "trello": ("trello",)}

SYSTEM_PROMPT = """\
You are helping an assessor evaluate a team's progress on a software \
development assignment, using only the evidence provided: a set of PROJECT \
FACTS computed from a complete database, and RETRIEVED EXTRACTS from \
individual commits, issues, code-review comments, and Trello card activity.

Your job is to give the assessor a clear picture of what each contributor \
actually did, not just whether the project as a whole is moving. Wherever \
the evidence spans more than one contributor, break the answer down by \
person rather than describing the team as a single unit.

Rules:
1. For any number - commit counts, totals, dates, who contributed how much - \
use the PROJECT FACTS. They are computed over every record and are complete.
2. Use the RETRIEVED EXTRACTS for qualitative detail: what was built, what \
was discussed, what problems came up, and the substance/quality of each \
contributor's work. Check its heading: if it says "a relevant sample", never \
count them or treat their absence as proof something did not happen. If it \
says "complete for the given time window" instead, every matching record in \
that window was read directly from the database, so you may treat counts \
and absences within that window the same way you would the facts.
3. Call out imbalance explicitly where the evidence shows it - who has been \
active versus quiet, whose commits carry substantive changes versus trivial \
ones. An assessor needs to see uneven contribution, not just team totals.
4. If the evidence does not answer the question, say so plainly and state \
what would be needed. Do not speculate or fill gaps with plausible detail.
5. Cite specific evidence where it supports a claim - commit shas, issue \
numbers, contributor names.
6. Be concise and concrete. Lead with the answer, then the support for it.\
"""


@dataclass
class QueryResult:
    """A generated answer plus everything needed to audit it."""

    question: str
    repo_id: int
    repo_name: str
    answer: str
    model: str
    stats: ProjectStats
    sources: list[RetrievedChunk]
    truncated_sources: int = 0
    complete_window: bool = False


def _since_to_datetime(since: date | None) -> datetime | None:
    """Turn a `since` date into the UTC instant it begins at, for comparison
    against the timezone-aware timestamps stored in Postgres and Chroma."""
    if since is None:
        return None
    return datetime.combine(since, time.min, tzinfo=timezone.utc)


def _strip_diff(chunk: RetrievedChunk) -> str:
    """
    Drop the code diff from a commit chunk's text, keeping the header,
    message, and files-changed/+-line summary above it.

    This tool tracks student activity and contribution, not code detail, so
    the diff is dead weight in the prompt: it pads out the context with
    material the assessor use case doesn't need, and buries each chunk's
    date among thousands of characters of unrelated diff lines (some of
    which - e.g. timestamps inside a Colab notebook diff - can themselves
    look like dates, confusing a small model asked to reason about recency).
    The +A/-D counts already carried in the header are enough signal for
    "substantive vs trivial" judgments without the diff itself.

    `commit_chunker.py` always introduces the diff with a literal "Diff:\\n"
    marker; discussion chunks (issues/comments) have no such marker and pass
    through unchanged.
    """
    if chunk.source_type != "commit":
        return chunk.text
    return chunk.text.split("Diff:\n", 1)[0].rstrip()


def _format_source(index: int, chunk: RetrievedChunk) -> str:
    """Render one retrieved chunk as a numbered, labelled extract."""
    header = (
        f"[{index}] {chunk.source_type} | author: {chunk.author} | "
        f"date: {chunk.timestamp[:10]} | id: {chunk.chunk_id}"
    )
    return f"{header}\n{_strip_diff(chunk)}"


def _build_context(chunks: list[RetrievedChunk], budget: int) -> tuple[str, int]:
    """
    Concatenate rendered chunks until the character budget runs out.

    Returns the context block and how many chunks were dropped. Chunks arrive
    newest-first (see retrieve_chunks), so dropping from the tail sheds the
    oldest material first - the whole list was already filtered to the most
    relevant chunks before ordering, so recency is the more useful tiebreak
    for what survives a tight budget. This bound is what stops a few
    thousand-line diffs from overflowing the model's context window - which
    fails as a confused answer rather than a clean error, so it is worth
    enforcing here.
    """
    parts: list[str] = []
    used = 0

    for index, chunk in enumerate(chunks, start=1):
        rendered = _format_source(index, chunk)
        if used + len(rendered) > budget and parts:
            return "\n\n".join(parts), len(chunks) - len(parts)
        parts.append(rendered)
        used += len(rendered)

    return "\n\n".join(parts), 0


def retrieve_chunks(
    repo: Repo,
    question: str,
    since: datetime | None = None,
    sources: tuple[str, ...] = SOURCES,
) -> list[RetrievedChunk]:
    """
    Search both of the repo's collections and return hits ordered by recency.

    Always searches commits and discussions together - rather than requiring
    the caller to pick a content type up front - so the model can draw on
    whichever kind of evidence the question actually needs.

    The repo's Chroma collections may be shared with other repos in the same
    group, so results are always scoped to this repo's own chunks via a
    metadata filter. `since`, if given, additionally restricts results to
    chunks timestamped on or after that instant.

    Which chunks make it into the sample is still decided by relevance
    (Chroma distance); only the order they're returned in is changed. Once
    selected, ISO timestamps sort correctly as plain strings, so a newest-
    first re-sort is enough - no parsing needed. This is a small model
    reading a short list, not a database query planner: putting the most
    recent chunk first makes "what's the most recent commit/comment" - a
    question the weekly-report use case asks constantly - answerable by
    reading the top of the list instead of comparing N scattered dates.
    """
    top_k = settings.retrieval_top_k
    namespace = repo.namespace
    conditions: list[dict] = [{"repo_name": repo.name}]
    if since is not None:
        conditions.append({"timestamp": {"$gte": since.isoformat()}})
    where = conditions[0] if len(conditions) == 1 else {"$and": conditions}

    content_types = [c for s in sources for c in SOURCE_CONTENT_TYPES[s]]
    hits: list[RetrievedChunk] = []
    for content in content_types:
        hits.extend(
            search(
                collection_name(namespace, content),
                query_text=question,
                n_results=top_k,
                where=where,
            )
        )

    # Chroma distances are comparable across these collections because both
    # are built with the same embedding model and distance function.
    hits.sort(key=lambda hit: hit.distance)
    selected = hits[: top_k * len(content_types)]
    selected.sort(key=lambda hit: hit.timestamp, reverse=True)
    return selected


def _fetch_complete_window(
    db: Session, repo: Repo, since: datetime, sources: tuple[str, ...] = SOURCES
) -> list[RetrievedChunk] | None:
    """
    Read every commit/issue/comment in [since, now) for this repo directly
    from Postgres, formatted exactly as ingestion would have chunked it -
    see the README's "Future work" section for the motivation.

    Returns None if the window holds more rows than
    COMPLETE_RETRIEVAL_ROW_LIMIT, so the caller falls back to Chroma's
    relevance-sampled retrieval instead of risking an unbounded prompt.
    Skipping Chroma here isn't just about completeness: embedding already
    happened once at ingest time, so this path costs a few indexed SQL
    queries and some string formatting - cheaper than a vector search, not
    more expensive.

    `ParsedCommit`/`RemoteIssue`/`RemoteIssueComment`/`RemoteReviewComment`
    are reused as adapters into the same `chunk_*` functions ingestion
    uses, so this path can't drift out of sync with what a real ingest
    would have produced. `diff_text` is left empty - the diff is stripped
    back out at render time regardless (`_strip_diff`), so there is no
    reason to pull potentially large diff text out of Postgres for this.
    """
    use_github = "github" in sources
    use_trello = "trello" in sources
    commits = db.scalars(
        select(Commit).where(Commit.repo_id == repo.id, Commit.committed_at >= since)
    ).all() if use_github else []
    issues = db.scalars(
        select(Issue).where(Issue.repo_id == repo.id, Issue.created_at >= since)
    ).all() if use_github else []
    # IssueComment has no repo_id of its own - join to Issue for both the
    # repo scope and the GitHub issue number `chunk_issue_comment` needs,
    # rather than lazy-loading `.issue` per row.
    comment_rows = db.execute(
        select(IssueComment, Issue.github_issue_number)
        .join(Issue, IssueComment.issue_id == Issue.id)
        .where(Issue.repo_id == repo.id, IssueComment.created_at >= since)
    ).all() if use_github else []
    review_comments = db.scalars(
        select(ReviewComment).where(ReviewComment.repo_id == repo.id, ReviewComment.created_at >= since)
    ).all() if use_github else []
    trello_actions = db.scalars(
        select(TrelloAction).where(TrelloAction.repo_id == repo.id, TrelloAction.created_at >= since)
    ).all() if use_trello else []

    total = (
        len(commits) + len(issues) + len(comment_rows) + len(review_comments) + len(trello_actions)
    )
    if total > settings.complete_retrieval_row_limit:
        return None

    chunks = [
        chunk_commit(
            ParsedCommit(
                sha=c.sha, author_name=c.author_name, author_email=c.author_email,
                committed_at=c.committed_at, message=c.message,
                files_changed=c.files_changed, additions=c.additions,
                deletions=c.deletions, diff_text="",
            ),
            repo_name=repo.name,
        )
        for c in commits
    ]
    chunks += [
        chunk_issue(
            RemoteIssue(number=i.github_issue_number, title=i.title, body=i.body,
                        author=i.author, state=i.state, created_at=i.created_at),
            repo_name=repo.name,
        )
        for i in issues
    ]
    chunks += [
        chunk_issue_comment(
            RemoteIssueComment(github_comment_id=ic.github_comment_id, issue_number=issue_number,
                                author=ic.author, body=ic.body, created_at=ic.created_at),
            repo_name=repo.name,
        )
        for ic, issue_number in comment_rows
    ]
    chunks += [
        chunk_review_comment(
            RemoteReviewComment(github_comment_id=rc.github_comment_id, pr_number=rc.pr_number,
                                 author=rc.author, body=rc.body, file_path=rc.file_path,
                                 line=rc.line, created_at=rc.created_at),
            repo_name=repo.name,
        )
        for rc in review_comments
    ]
    chunks += [
        chunk_trello_action(
            RemoteTrelloAction(trello_action_id=ta.trello_action_id, action_type=ta.action_type,
                                card_id=ta.card_id, card_name=ta.card_name,
                                member_creator=ta.member_creator, text=ta.text,
                                created_at=ta.created_at),
            repo_name=repo.name,
        )
        for ta in trello_actions
    ]

    # distance has no meaning here - nothing was ranked, everything in the
    # window is included - so it is set to 0.0 rather than left undefined.
    hits = [
        RetrievedChunk(chunk_id=c.chunk_id, text=c.text, metadata=c.chroma_metadata(), distance=0.0)
        for c in chunks
    ]
    hits.sort(key=lambda hit: hit.timestamp, reverse=True)
    return hits


def answer_question(
    db: Session,
    repo: Repo,
    question: str,
    since: date | None = None,
    sources: tuple[str, ...] = SOURCES,
) -> QueryResult:
    """
    Answer a natural-language question about one repo's activity.

    `since`, if given, scopes both the PROJECT FACTS and the RETRIEVED
    EXTRACTS to activity on or after that date, so e.g. "what happened last
    week" gets consistent facts and extracts rather than all-time totals
    alongside a recent-only sample.

    Raises ValueError if nothing has been ingested for the repo yet -
    answering from an empty index would produce a confident "no activity"
    that actually means "you never ran /ingest".
    """
    since_dt = _since_to_datetime(since)
    stats = collect_project_stats(db, repo, since=since_dt, sources=sources)
    if stats.is_empty:
        raise ValueError(
            f"No ingested {' or '.join(sources)} activity for this group"
            + (" in that window" if since else "")
            + ". Ingest it first."
        )

    chunks = _fetch_complete_window(db, repo, since_dt, sources) if since_dt is not None else None
    used_complete_window = chunks is not None
    if chunks is None:
        chunks = retrieve_chunks(repo, question, since=since_dt, sources=sources)

    context, dropped = _build_context(chunks, settings.max_context_chars)
    facts = format_stats_for_prompt(stats, sources)

    # The budget can still trim a complete window (a large window near the
    # row limit can still overflow MAX_CONTEXT_CHARS) - only claim
    # completeness in the prompt when nothing was actually dropped.
    complete_window = used_complete_window and dropped == 0
    extracts_label = (
        "RETRIEVED EXTRACTS (complete for the given time window, not a sample):"
        if complete_window else
        "RETRIEVED EXTRACTS (a relevant sample, not a complete list):"
    )

    user_prompt = (
        f"PROJECT FACTS (complete, computed from the database):\n"
        f"{facts}\n\n"
        f"{extracts_label}\n"
        f"{context or '(no matching extracts found)'}\n\n"
        f"QUESTION: {question}"
    )

    with OllamaClient() as llm:
        generated = llm.chat(system_prompt=SYSTEM_PROMPT, user_prompt=user_prompt)

    return QueryResult(
        question=question,
        repo_id=repo.id,
        repo_name=repo.name,
        answer=generated.text,
        model=generated.model,
        stats=stats,
        sources=chunks[: len(chunks) - dropped],
        truncated_sources=dropped,
        complete_window=complete_window,
    )
