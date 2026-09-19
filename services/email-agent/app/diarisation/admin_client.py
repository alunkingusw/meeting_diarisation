"""Client for meeting_diarisation's service-key-gated /admin/* endpoints (backend/routes/admin.py
there) - deliberately separate from client.py's per-user-JWT DiarisationClient, so the two
credential types stay structurally distinct in this codebase, not just by convention. Never
used to act on behalf of a user; only to read data no single user's JWT should be used for.
"""
from __future__ import annotations

import httpx


class AdminDiarisationApiError(Exception):
    """Raised on any non-2xx response from an /admin/* call."""


class AdminDiarisationClient:
    def __init__(self, base_url: str, service_api_key: str, timeout: float = 10.0):
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout)
        self._service_api_key = service_api_key

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "AdminDiarisationClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def get_group_owners(self) -> dict[str, int]:
        """GET /admin/group-owners - email -> backend user_id, for every User with an email
        on file. Replaces the static authorisation.group_owners map in config.yaml."""
        try:
            resp = self._client.get(
                "/admin/group-owners", headers={"X-Service-Key": self._service_api_key}
            )
        except httpx.HTTPError as e:
            raise AdminDiarisationApiError(f"GET /admin/group-owners failed: {e}") from e
        if resp.status_code != 200:
            raise AdminDiarisationApiError(
                f"GET /admin/group-owners returned {resp.status_code}: {resp.text[:200]}"
            )
        return resp.json()
