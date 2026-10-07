"""
Chunks GitHub "discussion" data: issues, issue comments, and PR review
comments.

Chunking unit: one chunk per issue, per issue comment, and per review
comment - each treated as its own atomic contribution, the same way each
commit is its own chunk. This preserves *who said what, when* rather than
flattening a whole thread into one undifferentiated blob.

Note that every `source_id` here is a GitHub-assigned id, not a derived
value like a timestamp: two people can comment in the same second, so
timestamps do not uniquely identify a comment.
"""

from backend.project_rag.chunking.types import Chunk
from backend.project_rag.ingestion.github_api import RemoteIssue, RemoteIssueComment, RemoteReviewComment


def chunk_issue(issue: RemoteIssue, repo_name: str) -> Chunk:
    """One chunk for an issue's title + body."""
    text = (
        f"Issue #{issue.number} in {repo_name} opened by {issue.author} "
        f"on {issue.created_at.date().isoformat()} (state: {issue.state})\n"
        f"Title: {issue.title}\n"
        f"Body: {issue.body or ''}"
    )
    return Chunk(
        text=text,
        source_type="issue",
        source_id=str(issue.number),
        author=issue.author,
        timestamp=issue.created_at,
        repo_name=repo_name,
        metadata={"state": issue.state, "issue_number": issue.number},
    )


def chunk_issue_comment(comment: RemoteIssueComment, repo_name: str) -> Chunk:
    """One chunk per comment on an issue."""
    text = (
        f"Comment by {comment.author} on issue #{comment.issue_number} in {repo_name} "
        f"on {comment.created_at.date().isoformat()}\n{comment.body}"
    )
    return Chunk(
        text=text,
        source_type="issue_comment",
        source_id=str(comment.github_comment_id),
        author=comment.author,
        timestamp=comment.created_at,
        repo_name=repo_name,
        metadata={"issue_number": comment.issue_number},
    )


def chunk_review_comment(comment: RemoteReviewComment, repo_name: str) -> Chunk:
    """One chunk per inline PR review comment."""
    location = f"{comment.file_path}:{comment.line}" if comment.file_path else "unknown location"
    text = (
        f"Review comment by {comment.author} on PR #{comment.pr_number} "
        f"in {repo_name} at {location} on {comment.created_at.date().isoformat()}\n"
        f"{comment.body}"
    )
    return Chunk(
        text=text,
        source_type="review_comment",
        source_id=str(comment.github_comment_id),
        author=comment.author,
        timestamp=comment.created_at,
        repo_name=repo_name,
        metadata={
            "pr_number": comment.pr_number,
            "file_path": comment.file_path or "",
            "line": comment.line if comment.line is not None else -1,
        },
    )


def chunk_discussions(
    issues: list[RemoteIssue],
    issue_comments: list[RemoteIssueComment],
    review_comments: list[RemoteReviewComment],
    repo_name: str,
) -> list[Chunk]:
    """Convenience wrapper: chunk every discussion item for a repo."""
    chunks: list[Chunk] = [chunk_issue(i, repo_name) for i in issues]
    chunks += [chunk_issue_comment(c, repo_name) for c in issue_comments]
    chunks += [chunk_review_comment(c, repo_name) for c in review_comments]
    return chunks
