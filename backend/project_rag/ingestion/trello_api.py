"""
Trello REST API client for board activity: card comments, card creations,
and card moves between lists.

Unlike GitHub (see github_api.py), Trello has no local-clone equivalent for
any of this - a board has no git history - so everything here goes through
the API. Trello also authenticates differently: `key` and `token` are query
string params sent with every request, not an Authorization header.

Only three action types are fetched (`commentCard`, `createCard`,
`updateCard`) via the `filter` param - Trello's actions endpoint otherwise
returns dozens of low-signal event types (label/member changes, attachments,
board settings, etc.) that carry no discussion content or task-state
signal. `updateCard` itself fires for *any* card field change under one
type name, so it is filtered further here, after fetching: only moves
between lists (identifiable by `data.listBefore`/`data.listAfter`) are kept,
not cosmetic edits like a renamed card or a changed due date.

Ingestion is incremental (see app.services.ingest_service): callers pass
`since=repo.trello_last_synced_at` so a re-run only fetches new activity,
unlike this project's GitHub client, which always re-fetches everything.
"""

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from backend.config import settings

# Trello's actions endpoint accepts up to 1000 results per request and
# paginates via a `before` cursor (the id of the oldest action already
# seen) rather than page numbers. This caps how many such pages one fetch
# will follow, as a safety valve against a misbehaving endpoint - same
# rationale as github_api.MAX_PAGES.
PAGE_LIMIT = 1000
MAX_PAGES = 200

MAX_RATE_LIMIT_RETRIES = 3
MAX_RATE_LIMIT_WAIT_SECONDS = 60

ACTION_TYPES = "commentCard,createCard,updateCard"


class TrelloRateLimitError(RuntimeError):
    """Raised when Trello's rate limit could not be waited out in reasonable time."""


@dataclass
class RemoteTrelloAction:
    trello_action_id: str
    action_type: str  # "commentCard" | "createCard" | "updateCard"
    card_id: str
    card_name: str
    member_creator: str
    text: str
    created_at: datetime


def _parse_trello_ts(value: str) -> datetime:
    """Parse Trello's ISO-8601 timestamp (with milliseconds) into an aware UTC datetime."""
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _describe_action(action_type: str, data: dict, member_name: str, card_name: str) -> str | None:
    """
    Build the text stored for one action.

    `commentCard` has real prose to use as-is. `createCard`/`updateCard`
    carry no free text, so a short descriptive sentence is synthesized
    instead - mirrored on how header info is embedded for commits
    (see commit_chunker.py). Returns None for an `updateCard` that is not a
    list move (i.e. has no listBefore/listAfter), which the caller uses to
    drop the low-signal remainder of that action type.
    """
    if action_type == "commentCard":
        return data.get("text") or ""

    if action_type == "createCard":
        list_name = (data.get("list") or {}).get("name", "a list")
        return f"{member_name} created card '{card_name}' in list '{list_name}'"

    if action_type == "updateCard":
        list_before = data.get("listBefore")
        list_after = data.get("listAfter")
        if list_before is None or list_after is None:
            return None
        return (
            f"{member_name} moved card '{card_name}' "
            f"from '{list_before.get('name', '?')}' to '{list_after.get('name', '?')}'"
        )

    return None


def _parse_action(item: dict) -> RemoteTrelloAction | None:
    """Convert one raw Trello action dict into a RemoteTrelloAction, or None to drop it."""
    action_type = item["type"]
    data = item.get("data") or {}
    card = data.get("card") or {}
    creator = item.get("memberCreator") or {}
    member_name = creator.get("fullName") or creator.get("username") or "unknown"
    card_name = card.get("name", "")

    text = _describe_action(action_type, data, member_name, card_name)
    if text is None:
        return None

    return RemoteTrelloAction(
        trello_action_id=item["id"],
        action_type=action_type,
        card_id=card.get("id", ""),
        card_name=card_name,
        member_creator=member_name,
        text=text,
        created_at=_parse_trello_ts(item["date"]),
    )


class TrelloClient:
    """
    Thin wrapper around the Trello REST API for the endpoints this project
    needs. Instantiate once per ingestion run and reuse across calls so the
    underlying HTTP connection is pooled.

    Usable as a context manager:

        with TrelloClient() as client:
            actions = client.fetch_board_actions(board_id, since=last_synced)
    """

    def __init__(self, api_key: str | None = None, token: str | None = None):
        self._api_key = api_key if api_key is not None else settings.trello_api_key
        self._token = token if token is not None else settings.trello_token

        self._client = httpx.Client(
            base_url=settings.trello_api_base_url,
            params={"key": self._api_key, "token": self._token},
            timeout=30.0,
        )

    def __enter__(self) -> "TrelloClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def check_board_access(self, board_id: str) -> bool:
        """Check access to one board without fetching its activity."""
        if not self._api_key or not self._token:
            return False
        try:
            response = self._client.get(
                f"/boards/{quote(board_id, safe='')}",
                params={"fields": "id"},
                timeout=3.0,
            )
        except httpx.HTTPError:
            return False
        return response.is_success

    def _rate_limit_wait_seconds(self, response: httpx.Response) -> float | None:
        """
        Work out how long to wait before retrying, or None if this response
        is not a rate-limit rejection. Trello signals rate limiting with a
        plain 429, optionally with a Retry-After header; when the header is
        absent a short fixed backoff is used instead.
        """
        if response.status_code != 429:
            return None

        retry_after = response.headers.get("retry-after")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                return 1.0
        return 1.0

    def _get(self, url: str, params: dict | None = None) -> httpx.Response:
        """GET with bounded rate-limit retries."""
        for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
            response = self._client.get(url, params=params)
            wait = self._rate_limit_wait_seconds(response)
            if wait is None:
                response.raise_for_status()
                return response

            if wait > MAX_RATE_LIMIT_WAIT_SECONDS or attempt == MAX_RATE_LIMIT_RETRIES:
                raise TrelloRateLimitError(
                    f"Trello rate limit hit on {url}; needs a {wait:.0f}s wait. "
                    "Wait for the limit to reset and re-run the ingest."
                )
            time.sleep(wait)

        raise TrelloRateLimitError(f"Exhausted rate-limit retries on {url}")

    def fetch_board_actions(
        self, board_id: str, since: datetime | None = None
    ) -> list[RemoteTrelloAction]:
        """
        Fetch card comments, card creations, and card moves for a board,
        newest-first from Trello, since a given instant (or full history if
        `since` is None).

        Paginates via `before`, set to the oldest action id seen so far,
        until a page comes back short of PAGE_LIMIT (the last page) or
        MAX_PAGES is hit.
        """
        params: dict = {"filter": ACTION_TYPES, "limit": PAGE_LIMIT}
        if since is not None:
            params["since"] = since.isoformat()

        raw_actions: list[dict] = []
        before: str | None = None
        for _ in range(MAX_PAGES):
            page_params = dict(params)
            if before is not None:
                page_params["before"] = before

            batch = self._get(f"/boards/{board_id}/actions", params=page_params).json()
            if not batch:
                break
            raw_actions.extend(batch)
            if len(batch) < PAGE_LIMIT:
                break
            before = batch[-1]["id"]

        actions = []
        for item in raw_actions:
            parsed = _parse_action(item)
            if parsed is not None:
                actions.append(parsed)
        return actions
