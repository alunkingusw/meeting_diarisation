import httpx

from backend.config import settings


def check_group_connections(
    github_repo_url: str | None,
    trello_board_id: str | None,
) -> tuple[bool, bool]:
    if not github_repo_url and not trello_board_id:
        return False, False

    try:
        response = httpx.post(
            f"{settings.github_raginator_base_url.rstrip('/')}/connections/check",
            json={"github_url": github_repo_url, "trello_board_id": trello_board_id},
            timeout=settings.github_raginator_timeout_seconds,
        )
    except httpx.HTTPError:
        return False, False
    if not 200 <= response.status_code < 300:
        return False, False

    try:
        result = response.json()
    except ValueError:
        return False, False
    if not isinstance(result, dict):
        return False, False
    return result.get("github_connected") is True, result.get("trello_connected") is True