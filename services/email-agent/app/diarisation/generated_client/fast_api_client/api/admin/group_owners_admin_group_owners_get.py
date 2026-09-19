from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.group_owners_admin_group_owners_get_response_group_owners_admin_group_owners_get import (
    GroupOwnersAdminGroupOwnersGetResponseGroupOwnersAdminGroupOwnersGet,
)
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
        "url": "/admin/group-owners",
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> GroupOwnersAdminGroupOwnersGetResponseGroupOwnersAdminGroupOwnersGet | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = GroupOwnersAdminGroupOwnersGetResponseGroupOwnersAdminGroupOwnersGet.from_dict(response.json())

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
) -> Response[GroupOwnersAdminGroupOwnersGetResponseGroupOwnersAdminGroupOwnersGet | HTTPValidationError]:
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
) -> Response[GroupOwnersAdminGroupOwnersGetResponseGroupOwnersAdminGroupOwnersGet | HTTPValidationError]:
    """Group Owners

     email -> user_id for every User with an email on file. There is no separate
    "owner" role in this schema (users_groups is a plain many-to-many) - any User with an
    email is authorised to act through GroupAssessmentAgent; per-group scoping happens
    separately via that user's own group membership.

    Args:
        x_service_key (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GroupOwnersAdminGroupOwnersGetResponseGroupOwnersAdminGroupOwnersGet | HTTPValidationError]
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
) -> GroupOwnersAdminGroupOwnersGetResponseGroupOwnersAdminGroupOwnersGet | HTTPValidationError | None:
    """Group Owners

     email -> user_id for every User with an email on file. There is no separate
    "owner" role in this schema (users_groups is a plain many-to-many) - any User with an
    email is authorised to act through GroupAssessmentAgent; per-group scoping happens
    separately via that user's own group membership.

    Args:
        x_service_key (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GroupOwnersAdminGroupOwnersGetResponseGroupOwnersAdminGroupOwnersGet | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        x_service_key=x_service_key,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    x_service_key: str | Unset = UNSET,
) -> Response[GroupOwnersAdminGroupOwnersGetResponseGroupOwnersAdminGroupOwnersGet | HTTPValidationError]:
    """Group Owners

     email -> user_id for every User with an email on file. There is no separate
    "owner" role in this schema (users_groups is a plain many-to-many) - any User with an
    email is authorised to act through GroupAssessmentAgent; per-group scoping happens
    separately via that user's own group membership.

    Args:
        x_service_key (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GroupOwnersAdminGroupOwnersGetResponseGroupOwnersAdminGroupOwnersGet | HTTPValidationError]
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
) -> GroupOwnersAdminGroupOwnersGetResponseGroupOwnersAdminGroupOwnersGet | HTTPValidationError | None:
    """Group Owners

     email -> user_id for every User with an email on file. There is no separate
    "owner" role in this schema (users_groups is a plain many-to-many) - any User with an
    email is authorised to act through GroupAssessmentAgent; per-group scoping happens
    separately via that user's own group membership.

    Args:
        x_service_key (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GroupOwnersAdminGroupOwnersGetResponseGroupOwnersAdminGroupOwnersGet | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            x_service_key=x_service_key,
        )
    ).parsed
