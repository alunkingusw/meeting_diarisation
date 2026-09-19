"""Thin, deterministic wrapper over GitHub-RAGinator's REST API - one method per endpoint
actually used, mirroring app/diarisation/client.py's "explicit finite operations" principle.
No auth: GitHub-RAGinator has none today, matching how it's actually deployed (internal
network only, see ../deploy/docker-compose.yml).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import httpx
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential


class GithubRaginatorApiError(Exception):
    """Base class for all errors raised by GithubRaginatorClient."""


class NotFoundError(GithubRaginatorApiError):
    """404 - no such repo. Not retried."""


class ClientError(GithubRaginatorApiError):
    """Any other 4xx. Not retried."""


class TransientError(GithubRaginatorApiError):
    """Timeouts and 5xx - retried internally with backoff."""


@dataclass
class RepoSummary:
    id: int
    github_url: str
    group_name: Optional[str]


@dataclass
class QueryResult:
    answer: str


class GithubRaginatorClient:
    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
        max_retry_attempts: int = 3,
        retry_backoff_seconds: float = 1.0,
    ):
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout)
        self._retryer = Retrying(
            reraise=True,
            retry=retry_if_exception_type(TransientError),
            stop=stop_after_attempt(max_retry_attempts),
            wait=wait_exponential(multiplier=retry_backoff_seconds, min=retry_backoff_seconds),
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GithubRaginatorClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    # --- endpoint methods -------------------------------------------------

    def find_repo_by_group_name(self, group_name: str) -> Optional[RepoSummary]:
        """GET /repos, filtered client-side to the given group_name - GitHub-RAGinator has no
        query-by-group endpoint, and repo registration is 1:many with group (several repos can
        share a group), so this returns the first match rather than assuming exactly one."""
        resp = self._request("GET", "/repos")
        for r in resp.json():
            if r.get("group_name") == group_name:
                return RepoSummary(id=r["id"], github_url=r["github_url"], group_name=r.get("group_name"))
        return None

    def query(self, repo_id: int, question: str) -> QueryResult:
        """POST /query - retrieval + facts + LLM-synthesized answer for one repo."""
        resp = self._request("POST", "/query", json={"repo_id": repo_id, "question": question})
        return QueryResult(answer=resp.json()["answer"])

    # --- request plumbing --------------------------------------------------

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        return self._retryer(self._do_request, method, path, **kwargs)

    def _do_request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            resp = self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as e:
            raise TransientError(f"Timeout calling {method} {path}: {e}") from e
        except httpx.TransportError as e:
            raise TransientError(f"Transport error calling {method} {path}: {e}") from e

        if resp.status_code >= 500:
            raise TransientError(f"{method} {path} returned {resp.status_code}: {resp.text[:200]}")
        if resp.status_code == 404:
            raise NotFoundError(f"{method} {path} returned 404: {resp.text[:200]}")
        if resp.status_code >= 400:
            raise ClientError(f"{method} {path} returned {resp.status_code}: {resp.text[:200]}")
        return resp
