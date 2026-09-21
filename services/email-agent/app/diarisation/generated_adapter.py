"""Adapter for generated OpenAPI operations during incremental migration."""
from __future__ import annotations

import datetime
import json

import httpx

from app.diarisation.client import (
    AuthError,
    ClientError,
    ConflictError,
    MeetingComment,
    NotFoundError,
    TransientError,
)
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
from app.diarisation.generated_client.fast_api_client.api.meetings.upload_file_groups_group_id_meetings_meeting_id_upload_post import (
    sync_detailed as upload_file_detailed,
)
from app.diarisation.generated_client.fast_api_client.api.transcripts.search_groups_group_id_transcripts_search_post import (
    sync_detailed as search_transcripts_detailed,
)
from app.diarisation.generated_client.fast_api_client.models.alias_resolve_request import AliasResolveRequest
from app.diarisation.generated_client.fast_api_client.models.body_upload_file_groups_group_id_meetings_meeting_id_upload_post import (
    BodyUploadFileGroupsGroupIdMeetingsMeetingIdUploadPost,
)
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
from app.diarisation.generated_client.fast_api_client.models.transcript_search_request import (
    TranscriptSearchRequest,
)
from app.diarisation.generated_client.fast_api_client.types import Unset


class GeneratedDiarisationAdapter:
    def __init__(self, base_url: str, timeout: float):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def add_comment(
        self, token: str, group_id: int, meeting_id: int, comment: str
    ) -> MeetingComment:
        client = AuthenticatedClient(
            base_url=self._base_url,
            token=token,
            timeout=httpx.Timeout(self._timeout),
            raise_on_unexpected_status=False,
        )
        try:
            response = add_comment_detailed(
                group_id=group_id,
                meeting_id=meeting_id,
                client=client,
                body=MeetingCommentCreate(comment=comment),
            )
        except httpx.TimeoutException as exc:
            raise TransientError(
                f"Timeout calling POST /groups/{group_id}/meetings/{meeting_id}/comments: {exc}"
            ) from exc
        except httpx.TransportError as exc:
            raise TransientError(
                f"Transport error calling POST /groups/{group_id}/meetings/{meeting_id}/comments: {exc}"
            ) from exc
        finally:
            client.get_httpx_client().close()

        if response.status_code >= 500:
            raise TransientError(
                f"POST /groups/{group_id}/meetings/{meeting_id}/comments returned "
                f"{response.status_code}: {response.content[:200]}"
            )
        if response.status_code in (401, 403):
            raise AuthError(
                f"POST /groups/{group_id}/meetings/{meeting_id}/comments returned "
                f"{response.status_code}: {response.content[:200]}"
            )
        if response.status_code == 404:
            raise NotFoundError(
                f"POST /groups/{group_id}/meetings/{meeting_id}/comments returned 404"
            )
        if response.status_code == 409:
            raise ConflictError(
                f"POST /groups/{group_id}/meetings/{meeting_id}/comments returned 409"
            )
        if response.status_code >= 400:
            raise ClientError(
                f"POST /groups/{group_id}/meetings/{meeting_id}/comments returned "
                f"{response.status_code}: {response.content[:200]}"
            )
        if response.parsed is None:
            raise ClientError("Comment endpoint returned no comment response")

        result = response.parsed
        return MeetingComment(
            id=result.id,
            meeting_id=result.meeting_id,
            user_id=result.user_id,
            comment=result.comment,
            created=result.created.isoformat(),
        )

    def list_groups(self, token: str) -> list[dict]:
        client = self._authenticated(token)
        try:
            try:
                response = list_groups_detailed(client=client)
            except httpx.TimeoutException as exc:
                raise TransientError(f"Timeout calling GET /groups/: {exc}") from exc
            except httpx.TransportError as exc:
                raise TransientError(f"Transport error calling GET /groups/: {exc}") from exc
            self._raise_for_response(response.status_code, "GET /groups/")
            return json.loads(response.content)
        finally:
            client.get_httpx_client().close()

    def get_group(self, token: str, group_id: int):
        client = self._authenticated(token)
        try:
            try:
                response = get_group_detailed(group_id=group_id, client=client)
            except httpx.TimeoutException as exc:
                raise TransientError(f"Timeout calling GET /groups/{group_id}: {exc}") from exc
            except httpx.TransportError as exc:
                raise TransientError(
                    f"Transport error calling GET /groups/{group_id}: {exc}"
                ) from exc
            self._raise_for_response(response.status_code, f"GET /groups/{group_id}")
            return response.parsed
        finally:
            client.get_httpx_client().close()

    def add_attendee(self, token: str, group_id: int, meeting_id: int, member_id: int) -> dict:
        client = self._authenticated(token)
        try:
            response = add_attendee_detailed(
                group_id=group_id,
                meeting_id=meeting_id,
                client=client,
                body=MeetingAttendee(member_id=member_id),
            )
            self._raise_for_response(
                response.status_code,
                f"POST /groups/{group_id}/meetings/{meeting_id}/attendees",
            )
            return response.parsed.to_dict()
        finally:
            client.get_httpx_client().close()

    def resolve_aliases(
        self, token: str, group_id: int, names: list[str], source: str | None = "transcript_name"
    ) -> dict[str, int | None]:
        client = self._authenticated(token)
        try:
            response = resolve_aliases_detailed(
                group_id=group_id,
                client=client,
                body=AliasResolveRequest(names=names, source=source),
            )
            self._raise_for_response(response.status_code, f"POST /groups/{group_id}/aliases/resolve")
            return response.parsed.to_dict()
        finally:
            client.get_httpx_client().close()

    def search_transcripts(
        self,
        token: str,
        group_id: int,
        query: str,
        meeting_id: int | None = None,
    ) -> list[dict]:
        client = self._authenticated(token)
        try:
            response = search_transcripts_detailed(
                group_id=group_id,
                client=client,
                body=TranscriptSearchRequest(query=query, meeting_id=meeting_id),
            )
            self._raise_for_response(response.status_code, f"POST /groups/{group_id}/transcripts/search")
            return response.parsed.get("results", [])
        finally:
            client.get_httpx_client().close()

    def upload_file(
        self, token: str, group_id: int, meeting_id: int, filename: str, content: bytes
    ) -> dict:
        client = self._authenticated(token)
        try:
            response = upload_file_detailed(
                group_id=group_id,
                meeting_id=meeting_id,
                client=client,
                body=BodyUploadFileGroupsGroupIdMeetingsMeetingIdUploadPost(file=content.decode('utf-8')),
            )
            self._raise_for_response(
                response.status_code,
                f"POST /groups/{group_id}/meetings/{meeting_id}/upload/",
            )
            return response.parsed
        finally:
            client.get_httpx_client().close()

    def create_meeting(
        self,
        token: str,
        group_id: int,
        date: datetime.datetime,
        idempotency_key: str | None = None,
    ) -> dict:
        client = self._authenticated(token)
        try:
            response = create_meeting_detailed(
                group_id=group_id,
                client=client,
                body=MeetingCreateEdit(date=date),
                idempotency_key=idempotency_key if idempotency_key is not None else Unset(),
            )
            self._raise_for_response(response.status_code, f"POST /groups/{group_id}/meetings/")
            return json.loads(response.content)
        finally:
            client.get_httpx_client().close()

    def list_meetings(
        self,
        token: str,
        group_id: int,
        from_date: datetime.date | None = None,
        to_date: datetime.date | None = None,
    ) -> list[dict]:
        client = self._authenticated(token)
        try:
            response = list_meetings_detailed(
                group_id=group_id,
                client=client,
                from_date=from_date if from_date is not None else Unset(),
                to_date=to_date if to_date is not None else Unset(),
            )
            self._raise_for_response(response.status_code, f"GET /groups/{group_id}/meetings/")
            return json.loads(response.content)
        finally:
            client.get_httpx_client().close()

    def get_meeting(self, token: str, group_id: int, meeting_id: int) -> dict:
        client = self._authenticated(token)
        try:
            response = get_meeting_detailed(group_id=group_id, meeting_id=meeting_id, client=client)
            self._raise_for_response(
                response.status_code,
                f"GET /groups/{group_id}/meetings/{meeting_id}",
            )
            return json.loads(response.content)
        finally:
            client.get_httpx_client().close()

    def _authenticated(self, token: str) -> AuthenticatedClient:
        return AuthenticatedClient(
            base_url=self._base_url,
            token=token,
            timeout=httpx.Timeout(self._timeout),
            raise_on_unexpected_status=False,
        )

    @staticmethod
    def _raise_for_response(status_code: int, operation: str) -> None:
        if status_code >= 500:
            raise TransientError(f"{operation} returned {status_code}")
        if status_code in (401, 403):
            raise AuthError(f"{operation} returned {status_code}")
        if status_code == 404:
            raise NotFoundError(f"{operation} returned 404")
        if status_code == 409:
            raise ConflictError(f"{operation} returned 409")
        if status_code >= 400:
            raise ClientError(f"{operation} returned {status_code}")

    def login_for_email(self, email: str, service_api_key: str) -> str:
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
            raise TransientError(f"Timeout calling POST /admin/user-token: {exc}") from exc
        except httpx.TransportError as exc:
            raise TransientError(f"Transport error calling POST /admin/user-token: {exc}") from exc
        finally:
            client.get_httpx_client().close()

        if response.status_code >= 500:
            raise TransientError(f"POST /admin/user-token returned {response.status_code}")
        if response.status_code in (401, 403):
            raise AuthError(f"POST /admin/user-token returned {response.status_code}")
        if response.status_code == 404:
            raise NotFoundError("POST /admin/user-token returned 404: user not found")
        if response.status_code >= 400:
            raise ClientError(f"POST /admin/user-token returned {response.status_code}")
        if not isinstance(response.parsed, dict) or "access_token" not in response.parsed:
            raise ClientError("User-token endpoint returned no access token")
        return response.parsed["access_token"]
