"""Adapter for generated OpenAPI operations during incremental migration."""
from __future__ import annotations

import datetime
import json
from contextlib import contextmanager
from typing import Iterator

import httpx

from app.diarisation.client import ClientError, MeetingComment, TransientError, raise_for_status
from app.diarisation.generated_client.fast_api_client import AuthenticatedClient, Client
from app.diarisation.generated_client.fast_api_client.api.admin.user_token_admin_user_token_post import (
    sync_detailed as user_token_detailed,
)
from app.diarisation.generated_client.fast_api_client.api.groups.get_group_groups_group_id_get import (
    sync_detailed as get_group_detailed,
)
from app.diarisation.generated_client.fast_api_client.api.groups.list_groups_groups_get import (
    sync_detailed as list_groups_detailed,
)
from app.diarisation.generated_client.fast_api_client.api.aliases.resolve_aliases_groups_group_id_aliases_resolve_post import (
    sync_detailed as resolve_aliases_detailed,
)
from app.diarisation.generated_client.fast_api_client.api.meetings.add_attendee_groups_group_id_meetings_meeting_id_attendees_post import (
    sync_detailed as add_attendee_detailed,
)
from app.diarisation.generated_client.fast_api_client.api.meetings.create_meeting_groups_group_id_meetings_post import (
    sync_detailed as create_meeting_detailed,
)
from app.diarisation.generated_client.fast_api_client.api.meetings.get_meeting_groups_group_id_meetings_meeting_id_get import (
    sync_detailed as get_meeting_detailed,
)
from app.diarisation.generated_client.fast_api_client.api.meetings.list_meetings_groups_group_id_meetings_get import (
    sync_detailed as list_meetings_detailed,
)
from app.diarisation.generated_client.fast_api_client.api.meetings.add_meeting_comment_groups_group_id_meetings_meeting_id_comments_post import (
    sync_detailed as add_comment_detailed,
)
from app.diarisation.generated_client.fast_api_client.models.alias_resolve_request import AliasResolveRequest
from app.diarisation.generated_client.fast_api_client.models.meeting_attendee import MeetingAttendee
from app.diarisation.generated_client.fast_api_client.models.meeting_comment_create import (
    MeetingCommentCreate,
)
from app.diarisation.generated_client.fast_api_client.models.meeting_create_edit import (
    MeetingCreateEdit,
)
from app.diarisation.generated_client.fast_api_client.models.service_user_token_request import (
    ServiceUserTokenRequest,
)
from app.diarisation.generated_client.fast_api_client.types import Unset


class GeneratedDiarisationAdapter:
    def __init__(self, base_url: str, timeout: float):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    @contextmanager
    def _session(self, token: str, operation: str) -> Iterator[AuthenticatedClient]:
        """An authenticated client that is always closed, with network failures mapped to TransientError."""
        client = AuthenticatedClient(
            base_url=self._base_url,
            token=token,
            timeout=httpx.Timeout(self._timeout),
            raise_on_unexpected_status=False,
        )
        try:
            yield client
        except httpx.TimeoutException as exc:
            raise TransientError(f"Timeout calling {operation}: {exc}") from exc
        except httpx.TransportError as exc:
            raise TransientError(f"Transport error calling {operation}: {exc}") from exc
        finally:
            client.get_httpx_client().close()

    def login_for_email(self, email: str, service_api_key: str) -> str:
        operation = "POST /admin/user-token"
        client = Client(
            base_url=self._base_url,
            timeout=httpx.Timeout(self._timeout),
            raise_on_unexpected_status=False,
        )
        try:
            response = user_token_detailed(
                client=client,
                body=ServiceUserTokenRequest(email=email),
                x_service_key=service_api_key,
            )
        except httpx.TimeoutException as exc:
            raise TransientError(f"Timeout calling {operation}: {exc}") from exc
        except httpx.TransportError as exc:
            raise TransientError(f"Transport error calling {operation}: {exc}") from exc
        finally:
            client.get_httpx_client().close()

        raise_for_status(response.status_code, operation, response.content.decode(errors="replace"))
        if not isinstance(response.parsed, dict) or "access_token" not in response.parsed:
            raise ClientError("User-token endpoint returned no access token")
        return response.parsed["access_token"]

    def list_groups(self, token: str) -> list[dict]:
        operation = "GET /groups/"
        with self._session(token, operation) as client:
            response = list_groups_detailed(client=client)
        raise_for_status(response.status_code, operation)
        return json.loads(response.content)

    def get_group(self, token: str, group_id: int):
        operation = f"GET /groups/{group_id}"
        with self._session(token, operation) as client:
            response = get_group_detailed(group_id=group_id, client=client)
        raise_for_status(response.status_code, operation)
        return response.parsed

    def create_meeting(
        self,
        token: str,
        group_id: int,
        date: datetime.datetime,
        idempotency_key: str | None = None,
    ) -> dict:
        operation = f"POST /groups/{group_id}/meetings/"
        with self._session(token, operation) as client:
            response = create_meeting_detailed(
                group_id=group_id,
                client=client,
                body=MeetingCreateEdit(date=date),
                idempotency_key=idempotency_key if idempotency_key is not None else Unset(),
            )
        raise_for_status(response.status_code, operation)
        return json.loads(response.content)

    def list_meetings(
        self,
        token: str,
        group_id: int,
        from_date: datetime.date | None = None,
        to_date: datetime.date | None = None,
    ) -> list[dict]:
        operation = f"GET /groups/{group_id}/meetings/"
        with self._session(token, operation) as client:
            response = list_meetings_detailed(
                group_id=group_id,
                client=client,
                from_date=from_date if from_date is not None else Unset(),
                to_date=to_date if to_date is not None else Unset(),
            )
        raise_for_status(response.status_code, operation)
        return json.loads(response.content)

    def get_meeting(self, token: str, group_id: int, meeting_id: int) -> dict:
        operation = f"GET /groups/{group_id}/meetings/{meeting_id}"
        with self._session(token, operation) as client:
            response = get_meeting_detailed(group_id=group_id, meeting_id=meeting_id, client=client)
        raise_for_status(response.status_code, operation)
        return json.loads(response.content)

    def add_attendee(self, token: str, group_id: int, meeting_id: int, member_id: int) -> dict:
        operation = f"POST /groups/{group_id}/meetings/{meeting_id}/attendees"
        with self._session(token, operation) as client:
            response = add_attendee_detailed(
                group_id=group_id,
                meeting_id=meeting_id,
                client=client,
                body=MeetingAttendee(member_id=member_id),
            )
        raise_for_status(response.status_code, operation)
        return response.parsed.to_dict()

    def add_comment(self, token: str, group_id: int, meeting_id: int, comment: str) -> MeetingComment:
        operation = f"POST /groups/{group_id}/meetings/{meeting_id}/comments"
        with self._session(token, operation) as client:
            response = add_comment_detailed(
                group_id=group_id,
                meeting_id=meeting_id,
                client=client,
                body=MeetingCommentCreate(comment=comment),
            )
        raise_for_status(response.status_code, operation, response.content.decode(errors="replace"))
        if response.parsed is None:
            raise ClientError("Comment endpoint returned no comment response")
        result = response.parsed
        return MeetingComment(
            id=result.id,
            meeting_id=result.meeting_id,
            user_id=result.user_id,
            comment=result.comment,
            created=result.created.isoformat(),
            group_member_id=result.group_member_id,
        )

    def resolve_aliases(
        self, token: str, group_id: int, names: list[str], source: str | None = "transcript_name"
    ) -> dict[str, int | None]:
        operation = f"POST /groups/{group_id}/aliases/resolve"
        with self._session(token, operation) as client:
            response = resolve_aliases_detailed(
                group_id=group_id,
                client=client,
                body=AliasResolveRequest(names=names, source=source),
            )
        raise_for_status(response.status_code, operation)
        return response.parsed.to_dict()

    def upload_file(
        self, token: str, group_id: int, meeting_id: int, filename: str, content: bytes
    ) -> dict:
        operation = f"POST /groups/{group_id}/meetings/{meeting_id}/upload/"
        lower_name = filename.lower()
        if lower_name.endswith(".vtt"):
            content_type = "text/vtt"
        elif lower_name.endswith(".srt"):
            content_type = "text/plain"
        else:
            content_type = "application/octet-stream"

        with self._session(token, operation) as client:
            response = client.get_httpx_client().request(
                "POST",
                f"/groups/{group_id}/meetings/{meeting_id}/upload/",
                files={"file": (filename, content, content_type)},
            )
        raise_for_status(response.status_code, operation)
        return response.json()
