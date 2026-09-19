import datetime
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
    *,
    from_date: datetime.date | None | Unset = UNSET,
    to_date: datetime.date | None | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_from_date: None | str | Unset
    if isinstance(from_date, Unset):
        json_from_date = UNSET
    elif isinstance(from_date, datetime.date):
        json_from_date = from_date.isoformat()
    else:
        json_from_date = from_date
    params["from_date"] = json_from_date

    json_to_date: None | str | Unset
    if isinstance(to_date, Unset):
        json_to_date = UNSET
    elif isinstance(to_date, datetime.date):
        json_to_date = to_date.isoformat()
    else:
        json_to_date = to_date
    params["to_date"] = json_to_date

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/groups/{group_id}/meetings/".format(
            group_id=quote(str(group_id), safe=""),
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
    *,
    client: AuthenticatedClient,
    from_date: datetime.date | None | Unset = UNSET,
    to_date: datetime.date | None | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """List Meetings

    Args:
        group_id (int):
        from_date (datetime.date | None | Unset): Include meetings on or after this date
        to_date (datetime.date | None | Unset): Include meetings on or before this date

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        group_id=group_id,
        from_date=from_date,
        to_date=to_date,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    group_id: int,
    *,
    client: AuthenticatedClient,
    from_date: datetime.date | None | Unset = UNSET,
    to_date: datetime.date | None | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """List Meetings

    Args:
        group_id (int):
        from_date (datetime.date | None | Unset): Include meetings on or after this date
        to_date (datetime.date | None | Unset): Include meetings on or before this date

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        group_id=group_id,
        client=client,
        from_date=from_date,
        to_date=to_date,
    ).parsed


async def asyncio_detailed(
    group_id: int,
    *,
    client: AuthenticatedClient,
    from_date: datetime.date | None | Unset = UNSET,
    to_date: datetime.date | None | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """List Meetings

    Args:
        group_id (int):
        from_date (datetime.date | None | Unset): Include meetings on or after this date
        to_date (datetime.date | None | Unset): Include meetings on or before this date

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        group_id=group_id,
        from_date=from_date,
        to_date=to_date,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    group_id: int,
    *,
    client: AuthenticatedClient,
    from_date: datetime.date | None | Unset = UNSET,
    to_date: datetime.date | None | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """List Meetings

    Args:
        group_id (int):
        from_date (datetime.date | None | Unset): Include meetings on or after this date
        to_date (datetime.date | None | Unset): Include meetings on or before this date

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            group_id=group_id,
            client=client,
            from_date=from_date,
            to_date=to_date,
        )
    ).parsed
