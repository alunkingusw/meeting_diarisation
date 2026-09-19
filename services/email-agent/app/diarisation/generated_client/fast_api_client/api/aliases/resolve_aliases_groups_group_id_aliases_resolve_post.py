from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.alias_resolve_request import AliasResolveRequest
from ...models.http_validation_error import HTTPValidationError
from ...models.resolve_aliases_groups_group_id_aliases_resolve_post_response_resolve_aliases_groups_group_id_aliases_resolve_post import (
    ResolveAliasesGroupsGroupIdAliasesResolvePostResponseResolveAliasesGroupsGroupIdAliasesResolvePost,
)
from ...types import Response


def _get_kwargs(
    group_id: int,
    *,
    body: AliasResolveRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/groups/{group_id}/aliases/resolve".format(
            group_id=quote(str(group_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    HTTPValidationError
    | ResolveAliasesGroupsGroupIdAliasesResolvePostResponseResolveAliasesGroupsGroupIdAliasesResolvePost
    | None
):
    if response.status_code == 200:
        response_200 = ResolveAliasesGroupsGroupIdAliasesResolvePostResponseResolveAliasesGroupsGroupIdAliasesResolvePost.from_dict(
            response.json()
        )

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
) -> Response[
    HTTPValidationError
    | ResolveAliasesGroupsGroupIdAliasesResolvePostResponseResolveAliasesGroupsGroupIdAliasesResolvePost
]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    group_id: int,
    *,
    client: AuthenticatedClient,
    body: AliasResolveRequest,
) -> Response[
    HTTPValidationError
    | ResolveAliasesGroupsGroupIdAliasesResolvePostResponseResolveAliasesGroupsGroupIdAliasesResolvePost
]:
    """Resolve Aliases

     Match each given name against this group's members by exact,
    case-insensitive name comparison. `source` is accepted but not
    currently used to vary matching behaviour.

    Args:
        group_id (int):
        body (AliasResolveRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ResolveAliasesGroupsGroupIdAliasesResolvePostResponseResolveAliasesGroupsGroupIdAliasesResolvePost]
    """

    kwargs = _get_kwargs(
        group_id=group_id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    group_id: int,
    *,
    client: AuthenticatedClient,
    body: AliasResolveRequest,
) -> (
    HTTPValidationError
    | ResolveAliasesGroupsGroupIdAliasesResolvePostResponseResolveAliasesGroupsGroupIdAliasesResolvePost
    | None
):
    """Resolve Aliases

     Match each given name against this group's members by exact,
    case-insensitive name comparison. `source` is accepted but not
    currently used to vary matching behaviour.

    Args:
        group_id (int):
        body (AliasResolveRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ResolveAliasesGroupsGroupIdAliasesResolvePostResponseResolveAliasesGroupsGroupIdAliasesResolvePost
    """

    return sync_detailed(
        group_id=group_id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    group_id: int,
    *,
    client: AuthenticatedClient,
    body: AliasResolveRequest,
) -> Response[
    HTTPValidationError
    | ResolveAliasesGroupsGroupIdAliasesResolvePostResponseResolveAliasesGroupsGroupIdAliasesResolvePost
]:
    """Resolve Aliases

     Match each given name against this group's members by exact,
    case-insensitive name comparison. `source` is accepted but not
    currently used to vary matching behaviour.

    Args:
        group_id (int):
        body (AliasResolveRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ResolveAliasesGroupsGroupIdAliasesResolvePostResponseResolveAliasesGroupsGroupIdAliasesResolvePost]
    """

    kwargs = _get_kwargs(
        group_id=group_id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    group_id: int,
    *,
    client: AuthenticatedClient,
    body: AliasResolveRequest,
) -> (
    HTTPValidationError
    | ResolveAliasesGroupsGroupIdAliasesResolvePostResponseResolveAliasesGroupsGroupIdAliasesResolvePost
    | None
):
    """Resolve Aliases

     Match each given name against this group's members by exact,
    case-insensitive name comparison. `source` is accepted but not
    currently used to vary matching behaviour.

    Args:
        group_id (int):
        body (AliasResolveRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ResolveAliasesGroupsGroupIdAliasesResolvePostResponseResolveAliasesGroupsGroupIdAliasesResolvePost
    """

    return (
        await asyncio_detailed(
            group_id=group_id,
            client=client,
            body=body,
        )
    ).parsed
