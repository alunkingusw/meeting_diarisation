from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.meeting_out import MeetingOut
from ...types import Response


def _get_kwargs(
    group_id: int,
    meeting_id: int,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/groups/{group_id}/meetings/{meeting_id}".format(
            group_id=quote(str(group_id), safe=""),
            meeting_id=quote(str(meeting_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | MeetingOut | None:
    if response.status_code == 200:
        response_200 = MeetingOut.from_dict(response.json())

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
) -> Response[HTTPValidationError | MeetingOut]:
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
) -> Response[HTTPValidationError | MeetingOut]:
    """Get Meeting

    Args:
        group_id (int):
        meeting_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | MeetingOut]
    """

    kwargs = _get_kwargs(
        group_id=group_id,
        meeting_id=meeting_id,
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
) -> HTTPValidationError | MeetingOut | None:
    """Get Meeting

    Args:
        group_id (int):
        meeting_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | MeetingOut
    """

    return sync_detailed(
        group_id=group_id,
        meeting_id=meeting_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    group_id: int,
    meeting_id: int,
    *,
    client: AuthenticatedClient,
) -> Response[HTTPValidationError | MeetingOut]:
    """Get Meeting

    Args:
        group_id (int):
        meeting_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | MeetingOut]
    """

    kwargs = _get_kwargs(
        group_id=group_id,
        meeting_id=meeting_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    group_id: int,
    meeting_id: int,
    *,
    client: AuthenticatedClient,
) -> HTTPValidationError | MeetingOut | None:
    """Get Meeting

    Args:
        group_id (int):
        meeting_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | MeetingOut
    """

    return (
        await asyncio_detailed(
            group_id=group_id,
            meeting_id=meeting_id,
            client=client,
        )
    ).parsed
