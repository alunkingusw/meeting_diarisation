from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.service_user_token_request import ServiceUserTokenRequest
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    body: ServiceUserTokenRequest,
    x_service_key: str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_service_key, Unset):
        headers["x-service-key"] = x_service_key

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/admin/user-token",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
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
    *,
    client: AuthenticatedClient | Client,
    body: ServiceUserTokenRequest,
    x_service_key: str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """User Token

     Resolve a verified service-caller email to a short-lived user JWT.

    The service key authenticates the email agent; the returned JWT keeps all existing
    group-level authorization checks in one place. The agent must verify the inbound
    message's sender authentication before calling this endpoint.

    Args:
        x_service_key (str | Unset):
        body (ServiceUserTokenRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        body=body,
        x_service_key=x_service_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    body: ServiceUserTokenRequest,
    x_service_key: str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """User Token

     Resolve a verified service-caller email to a short-lived user JWT.

    The service key authenticates the email agent; the returned JWT keeps all existing
    group-level authorization checks in one place. The agent must verify the inbound
    message's sender authentication before calling this endpoint.

    Args:
        x_service_key (str | Unset):
        body (ServiceUserTokenRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        body=body,
        x_service_key=x_service_key,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: ServiceUserTokenRequest,
    x_service_key: str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """User Token

     Resolve a verified service-caller email to a short-lived user JWT.

    The service key authenticates the email agent; the returned JWT keeps all existing
    group-level authorization checks in one place. The agent must verify the inbound
    message's sender authentication before calling this endpoint.

    Args:
        x_service_key (str | Unset):
        body (ServiceUserTokenRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        body=body,
        x_service_key=x_service_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: ServiceUserTokenRequest,
    x_service_key: str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """User Token

     Resolve a verified service-caller email to a short-lived user JWT.

    The service key authenticates the email agent; the returned JWT keeps all existing
    group-level authorization checks in one place. The agent must verify the inbound
    message's sender authentication before calling this endpoint.

    Args:
        x_service_key (str | Unset):
        body (ServiceUserTokenRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
            x_service_key=x_service_key,
        )
    ).parsed
