from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.group_project_info import GroupProjectInfo
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    x_service_key: str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_service_key, Unset):
        headers["x-service-key"] = x_service_key

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/admin/groups",
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | list[GroupProjectInfo] | None:
    if response.status_code == 200:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in _response_200:
            response_200_item = GroupProjectInfo.from_dict(response_200_item_data)

            response_200.append(response_200_item)

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
) -> Response[HTTPValidationError | list[GroupProjectInfo]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    x_service_key: str | Unset = UNSET,
) -> Response[HTTPValidationError | list[GroupProjectInfo]]:
    """Groups

     Every group that has a GitHub repo linked, for GitHub-RAGinator's
    scripts/sync_repos_from_diarisation.py to mirror into its own repo registration. Groups
    with no github_repo_url set are omitted - there is nothing for that script to do with them.

    Args:
        x_service_key (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[GroupProjectInfo]]
    """

    kwargs = _get_kwargs(
        x_service_key=x_service_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    x_service_key: str | Unset = UNSET,
) -> HTTPValidationError | list[GroupProjectInfo] | None:
    """Groups

     Every group that has a GitHub repo linked, for GitHub-RAGinator's
    scripts/sync_repos_from_diarisation.py to mirror into its own repo registration. Groups
    with no github_repo_url set are omitted - there is nothing for that script to do with them.

    Args:
        x_service_key (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[GroupProjectInfo]
    """

    return sync_detailed(
        client=client,
        x_service_key=x_service_key,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    x_service_key: str | Unset = UNSET,
) -> Response[HTTPValidationError | list[GroupProjectInfo]]:
    """Groups

     Every group that has a GitHub repo linked, for GitHub-RAGinator's
    scripts/sync_repos_from_diarisation.py to mirror into its own repo registration. Groups
    with no github_repo_url set are omitted - there is nothing for that script to do with them.

    Args:
        x_service_key (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[GroupProjectInfo]]
    """

    kwargs = _get_kwargs(
        x_service_key=x_service_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    x_service_key: str | Unset = UNSET,
) -> HTTPValidationError | list[GroupProjectInfo] | None:
    """Groups

     Every group that has a GitHub repo linked, for GitHub-RAGinator's
    scripts/sync_repos_from_diarisation.py to mirror into its own repo registration. Groups
    with no github_repo_url set are omitted - there is nothing for that script to do with them.

    Args:
        x_service_key (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[GroupProjectInfo]
    """

    return (
        await asyncio_detailed(
            client=client,
            x_service_key=x_service_key,
        )
    ).parsed
