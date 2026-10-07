from backend.project_rag.ingestion.github_api import GitHubClient
from backend.project_rag.ingestion.trello_api import TrelloClient


def check_group_connections(
    github_repo_url: str | None,
    trello_board_id: str | None,
) -> tuple[bool, bool]:
    """Probe the linked repo and board with the configured credentials."""
    github_connected = False
    if github_repo_url:
        with GitHubClient() as github:
            github_connected = github.check_repo_access(github_repo_url)

    trello_connected = False
    if trello_board_id:
        with TrelloClient() as trello:
            trello_connected = trello.check_board_access(trello_board_id)

    return github_connected, trello_connected
