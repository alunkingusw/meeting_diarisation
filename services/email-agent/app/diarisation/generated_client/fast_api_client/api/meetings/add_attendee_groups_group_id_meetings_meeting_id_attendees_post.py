from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.group_member_out import GroupMemberOut
from ...models.http_validation_error import HTTPValidationError
from ...models.meeting_attendee import MeetingAttendee
from ...types import Response


def _get_kwargs(
    group_id: int,
    meeting_id: int,
    *,
    body: MeetingAttendee,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/groups/{group_id}/meetings/{meeting_id}/attendees".format(
            group_id=quote(str(group_id), safe=""),
            meeting_id=quote(str(meeting_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> GroupMemberOut | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = GroupMemberOut.from_dict(response.json())

        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[GroupMemberOut | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    group_id: int,
    meeting_id: int,
    *,
    client: AuthenticatedClient,
    body: MeetingAttendee,
) -> Response[GroupMemberOut | HTTPValidationError]:
    """Add Attendee

    Args:
        group_id (int):
        meeting_id (int):
        body (MeetingAttendee):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GroupMemberOut | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        group_id=group_id,
        meeting_id=meeting_id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    group_id: int,
    meeting_id: int,
    *,
    client: AuthenticatedClient,
    body: MeetingAttendee,
) -> GroupMemberOut | HTTPValidationError | None:
    """Add Attendee

    Args:
        group_id (int):
        meeting_id (int):
        body (MeetingAttendee):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GroupMemberOut | HTTPValidationError
    """

    return sync_detailed(
        group_id=group_id,
        meeting_id=meeting_id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    group_id: int,
    meeting_id: int,
    *,
    client: AuthenticatedClient,
    body: MeetingAttendee,
) -> Response[GroupMemberOut | HTTPValidationError]:
    """Add Attendee

    Args:
        group_id (int):
        meeting_id (int):
        body (MeetingAttendee):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GroupMemberOut | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        group_id=group_id,
        meeting_id=meeting_id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    group_id: int,
    meeting_id: int,
    *,
    client: AuthenticatedClient,
    body: MeetingAttendee,
) -> GroupMemberOut | HTTPValidationError | None:
    """Add Attendee

    Args:
        group_id (int):
        meeting_id (int):
        body (MeetingAttendee):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GroupMemberOut | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            group_id=group_id,
            meeting_id=meeting_id,
            client=client,
            body=body,
        )
    ).parsed
