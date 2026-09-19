from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    group_id: int,
    meeting_id: int,
    *,
    regenerate: bool | Unset = False,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["regenerate"] = regenerate

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/groups/{group_id}/meetings/{meeting_id}/summarise".format(
            group_id=quote(str(group_id), safe=""),
            meeting_id=quote(str(meeting_id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = response.json()
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
) -> Response[Any | HTTPValidationError]:
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
    regenerate: bool | Unset = False,
) -> Response[Any | HTTPValidationError]:
    """Summarise Meeting

     Returns this meeting's summary, generating it via the local LLM
    (backend/summarization) on first request if none is cached yet. Pass
    ?regenerate=true to force a fresh summary even if one is already stored -
    e.g. after the transcript has been corrected.

    Args:
        group_id (int):
        meeting_id (int):
        regenerate (bool | Unset):  Default: False.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        group_id=group_id,
        meeting_id=meeting_id,
        regenerate=regenerate,
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
    regenerate: bool | Unset = False,
) -> Any | HTTPValidationError | None:
    """Summarise Meeting

     Returns this meeting's summary, generating it via the local LLM
    (backend/summarization) on first request if none is cached yet. Pass
    ?regenerate=true to force a fresh summary even if one is already stored -
    e.g. after the transcript has been corrected.

    Args:
        group_id (int):
        meeting_id (int):
        regenerate (bool | Unset):  Default: False.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        group_id=group_id,
        meeting_id=meeting_id,
        client=client,
        regenerate=regenerate,
    ).parsed


async def asyncio_detailed(
    group_id: int,
    meeting_id: int,
    *,
    client: AuthenticatedClient,
    regenerate: bool | Unset = False,
) -> Response[Any | HTTPValidationError]:
    """Summarise Meeting

     Returns this meeting's summary, generating it via the local LLM
    (backend/summarization) on first request if none is cached yet. Pass
    ?regenerate=true to force a fresh summary even if one is already stored -
    e.g. after the transcript has been corrected.

    Args:
        group_id (int):
        meeting_id (int):
        regenerate (bool | Unset):  Default: False.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        group_id=group_id,
        meeting_id=meeting_id,
        regenerate=regenerate,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    group_id: int,
    meeting_id: int,
    *,
    client: AuthenticatedClient,
    regenerate: bool | Unset = False,
) -> Any | HTTPValidationError | None:
    """Summarise Meeting

     Returns this meeting's summary, generating it via the local LLM
    (backend/summarization) on first request if none is cached yet. Pass
    ?regenerate=true to force a fresh summary even if one is already stored -
    e.g. after the transcript has been corrected.

    Args:
        group_id (int):
        meeting_id (int):
        regenerate (bool | Unset):  Default: False.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            group_id=group_id,
            meeting_id=meeting_id,
            client=client,
            regenerate=regenerate,
        )
    ).parsed
