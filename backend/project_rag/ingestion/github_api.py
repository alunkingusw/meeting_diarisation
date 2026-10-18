"""
GitHub REST API client for data that does not live in the local git
history: issues, issue comments, and pull-request review comments.

Commits/diffs deliberately do NOT go through this client - they are read
from the local clone (see commit_parser.py) since that is faster and
avoids GitHub's API rate limits. This module only covers the
platform-level collaboration data that has no local equivalent.

Uses the REST API (rather than GraphQL) for simplicity. Every list is
fetched from a repo-wide endpoint rather than per-issue, so the number of
HTTP requests scales with total comment volume rather than with issue
count.
"""

import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from backend.config import settings

# Safety valve on pagination loops so a misbehaving endpoint can never spin
# forever. 100 items per page x 200 pages = 20,000 records per list.
MAX_PAGES = 200

# How many times to wait out a rate limit before giving up, and the longest
# single wait we are willing to sit through inside one ingest request.
MAX_RATE_LIMIT_RETRIES = 3
MAX_RATE_LIMIT_WAIT_SECONDS = 60


class GitHubRateLimitError(RuntimeError):
    """Raised when GitHub's rate limit could not be waited out in reasonable time."""


@dataclass
class RemoteIssue:
    number: int
    title: str
    body: str | None
    author: str
    state: str
    created_at: datetime


@dataclass
class RemoteIssueComment:
    github_comment_id: int
    issue_number: int
    author: str
    body: str
    created_at: datetime


@dataclass
class RemoteReviewComment:
    github_comment_id: int
    pr_number: int
    author: str
    body: str
    file_path: str | None
    line: int | None
    created_at: datetime


def _owner_repo_from_url(github_url: str) -> tuple[str, str]:
    """Extract (owner, repo) from a GitHub URL, e.g. .../org/repo -> ('org', 'repo')."""
    cleaned = github_url.rstrip("/").removesuffix(".git")
    match = re.search(r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/]+)$", cleaned)
    if not match:
        raise ValueError(f"Could not parse owner/repo from URL: {github_url}")
    return match.group("owner"), match.group("repo")


def _parse_github_ts(value: str) -> datetime:
    """
    Parse a GitHub ISO-8601 timestamp into a timezone-aware UTC datetime.

    GitHub returns "2024-01-01T12:00:00Z"; `fromisoformat` on Python < 3.11
    rejects the trailing "Z", hence the replace. Keeping everything aware and
    in UTC is what makes cross-store comparisons and week-bucketing safe.
    """
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _number_from_url(url: str) -> int:
    """Pull the trailing numeric id out of a GitHub API URL (.../issues/42 -> 42)."""
    return int(url.rstrip("/").split("/")[-1])


class GitHubClient:
    """
    Thin wrapper around the GitHub REST API for the endpoints this project
    needs. Instantiate once per ingestion run and reuse across calls so the
    underlying HTTP connection is pooled.

    Usable as a context manager:

        with GitHubClient() as client:
            issues = client.fetch_issues(url)
    """

    def __init__(self, token: str | None = None):
        self._token = token or settings.github_token
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        # Only send Authorization when there is an actual token. An empty
        # "Bearer " header is malformed, and GitHub answers it with 401 even
        # for public repos - so omitting it is what enables the unauthenticated
        # (60 requests/hour) fallback to work at all.
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        self._client = httpx.Client(
            base_url=settings.github_api_base_url,
            headers=headers,
            timeout=30.0,
        )

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def check_repo_access(self, github_url: str) -> bool:
        """Check access to one repository without fetching its activity."""
        try:
            owner, repo = _owner_repo_from_url(github_url)
            response = self._client.get(f"/repos/{owner}/{repo}", timeout=3.0)
        except (ValueError, httpx.HTTPError):
            return False
        return response.is_success

    def _rate_limit_wait_seconds(self, response: httpx.Response) -> float | None:
        """
        Work out how long to wait before retrying, or None if this response is
        not a rate-limit rejection.

        GitHub signals two different things with 403/429: the primary limit
        (x-ratelimit-remaining: 0, resets at x-ratelimit-reset) and secondary
        abuse limits (Retry-After). Both are handled here.
        """
        if response.status_code not in (403, 429):
            return None

        retry_after = response.headers.get("retry-after")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                return None

        if response.headers.get("x-ratelimit-remaining") == "0":
            reset_at = response.headers.get("x-ratelimit-reset")
            if reset_at:
                try:
                    # +1s of slack so we do not wake up a moment too early.
                    return max(0.0, float(reset_at) - time.time()) + 1.0
                except ValueError:
                    return None
        return None

    def _get(self, url: str, params: dict | None = None) -> httpx.Response:
        """GET with bounded rate-limit retries."""
        for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
            response = self._client.get(url, params=params)
            wait = self._rate_limit_wait_seconds(response)
            if wait is None:
                response.raise_for_status()
                return response

            if wait > MAX_RATE_LIMIT_WAIT_SECONDS or attempt == MAX_RATE_LIMIT_RETRIES:
                hint = (
                    "Set GITHUB_TOKEN in .env to raise the limit from 60 to 5,000 "
                    "requests/hour."
                    if not self._token
                    else "Wait for the limit to reset and re-run the ingest."
                )
                raise GitHubRateLimitError(
                    f"GitHub rate limit hit on {url}; needs a {wait:.0f}s wait. {hint}"
                )
            time.sleep(wait)

        raise GitHubRateLimitError(f"Exhausted rate-limit retries on {url}")

    def _paginated_get(self, url: str, params: dict | None = None) -> list[dict]:
        """
        Follow GitHub's `page`-based pagination and return all results.

        Stops on the first empty page, on a short page (fewer items than
        per_page, which means it was the last one), at MAX_PAGES, or on a 422
        - which is how GitHub rejects requests for pages past its own
        internal offset limit (observed ~10,000 results deep into a large
        repo's issue/comment history, e.g. numpy). That is GitHub's limit,
        not a malformed request, so the results gathered so far are returned
        rather than failing the whole ingest.
        """
        results: list[dict] = []
        params = dict(params or {})
        params["per_page"] = 100

        for page in range(1, MAX_PAGES + 1):
            params["page"] = page
            try:
                batch = self._get(url, params=params).json()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 422:
                    break
                raise
            if not batch:
                break
            results.extend(batch)
            if len(batch) < params["per_page"]:
                break

        return results

    def fetch_issues(self, github_url: str) -> list[RemoteIssue]:
        """
        Fetch all issues for a repo.

        Note: GitHub's issues endpoint also returns pull requests (a PR is
        technically an issue under the hood). We filter those out here
        since PR review comments are fetched separately via fetch_review_comments.
        """
        owner, repo = _owner_repo_from_url(github_url)
        raw_issues = self._paginated_get(f"/repos/{owner}/{repo}/issues", params={"state": "all"})

        issues = []
        for item in raw_issues:
            if "pull_request" in item:
                continue  # skip PRs, keep true issues only
            issues.append(
                RemoteIssue(
                    number=item["number"],
                    title=item["title"],
                    body=item.get("body"),
                    author=(item.get("user") or {}).get("login", "unknown"),
                    state=item["state"],
                    created_at=_parse_github_ts(item["created_at"]),
                )
            )
        return issues

    def fetch_issue_comments(self, github_url: str) -> list[RemoteIssueComment]:
        """
        Fetch every issue comment in the repo in one paginated sweep.

        Uses the repo-wide `/issues/comments` endpoint rather than
        `/issues/{n}/comments` per issue. Two consequences, both wanted:
        it is one request per 100 comments instead of one per issue, and new
        replies on *already-ingested* issues are picked up on a re-run
        instead of being missed.

        The response also includes comments on pull requests (PRs are issues
        under the hood); callers filter to the issues they actually store.
        """
        owner, repo = _owner_repo_from_url(github_url)
        raw_comments = self._paginated_get(f"/repos/{owner}/{repo}/issues/comments")

        return [
            RemoteIssueComment(
                github_comment_id=item["id"],
                issue_number=_number_from_url(item["issue_url"]),
                author=(item.get("user") or {}).get("login", "unknown"),
                body=item.get("body") or "",
                created_at=_parse_github_ts(item["created_at"]),
            )
            for item in raw_comments
        ]

    def fetch_review_comments(self, github_url: str) -> list[RemoteReviewComment]:
        """
        Fetch all pull-request review comments (inline code review comments)
        across the whole repo in one paginated call.
        """
        owner, repo = _owner_repo_from_url(github_url)
        raw_comments = self._paginated_get(f"/repos/{owner}/{repo}/pulls/comments")

        return [
            RemoteReviewComment(
                github_comment_id=item["id"],
                pr_number=_number_from_url(item["pull_request_url"]),
                author=(item.get("user") or {}).get("login", "unknown"),
                body=item.get("body") or "",
                file_path=item.get("path"),
                line=item.get("line"),
                created_at=_parse_github_ts(item["created_at"]),
            )
            for item in raw_comments
        ]
