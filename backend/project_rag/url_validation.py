"""GitHub URL validation shared by group create/edit and ingestion."""

import re
from urllib.parse import urlparse

from backend.config import settings

_GITHUB_PATH = re.compile(r"^/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")


def _allowed_hosts() -> set[str]:
    hosts = {"github.com", "www.github.com"}
    api_host = urlparse(settings.github_api_base_url).hostname
    if api_host:
        hosts.add(api_host)
        if api_host.startswith("api."):
            hosts.add(api_host[len("api.") :])
    return hosts


def validate_github_url(value: str) -> str:
    """Return the cleaned URL, or raise ValueError.

    The value is passed to `git clone`, so only https URLs on a known GitHub host
    pointing at owner/repo are accepted - never file://, ssh:// or internal hosts.
    """
    cleaned = value.strip().rstrip("/")
    parsed = urlparse(cleaned)

    if parsed.scheme != "https":
        raise ValueError("github_repo_url must be an https:// URL")
    if (parsed.hostname or "") not in _allowed_hosts():
        raise ValueError(f"github_repo_url host must be one of: {', '.join(sorted(_allowed_hosts()))}")
    if not _GITHUB_PATH.match(parsed.path.removesuffix(".git")):
        raise ValueError("github_repo_url must point at a repository, e.g. https://github.com/org/repo")
    return cleaned
