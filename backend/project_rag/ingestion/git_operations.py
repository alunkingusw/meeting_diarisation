"""
Local git operations: cloning and updating a repository on disk.

Rationale: `git log`/diff inspection operates on local files, and
repeatedly fetching that volume of data through the GitHub API would be
slower and burns through API rate limits fast. So the repo is cloned once,
then updated on each subsequent ingestion run.
"""

import re
from pathlib import Path

import git  # GitPython

from backend.config import settings


def _repo_name_from_url(github_url: str) -> str:
    """
    Derive a filesystem-safe folder name from a GitHub URL.

    e.g. "https://github.com/my-org/my-repo" -> "my-org__my-repo"

    The final `re.sub` is what keeps this safe: it strips anything that is
    not alphanumeric/underscore/hyphen, so "../.." style path traversal in a
    URL cannot escape REPO_STORAGE_DIR.
    """
    cleaned = github_url.rstrip("/").removesuffix(".git")
    parts = cleaned.split("/")[-2:]  # ["my-org", "my-repo"]
    safe = "__".join(parts)
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", safe)


def local_path_for(github_url: str) -> Path:
    """Return the local directory a given GitHub repo would be cloned into."""
    return Path(settings.repo_storage_dir) / _repo_name_from_url(github_url)


def _git_env() -> dict[str, str]:
    """
    Extra environment variables for git subprocesses. Merged into the
    existing environment by GitPython rather than replacing it.

    `GIT_TERMINAL_PROMPT=0` is essential: without it, cloning a private or
    non-existent repo makes git block forever waiting for credentials to be
    typed at a terminal that nobody is watching, which hangs the HTTP worker
    handling the ingest request. With it, git fails fast instead.
    """
    return {
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "",
        "SSH_ASKPASS": "",
    }


def _authenticated_url(github_url: str) -> str:
    """
    Inject the GitHub token into an https clone URL when one is configured.

    Lets private repos be cloned with the same token already used for the
    REST API, instead of requiring a separate credential helper or SSH key.
    The token is only ever passed to git via the remote URL of a local
    clone; it is never logged or returned to API callers.
    """
    token = settings.github_token
    if not token or not github_url.startswith("https://"):
        return github_url
    return github_url.replace("https://", f"https://x-access-token:{token}@", 1)


def clone_or_pull(github_url: str) -> Path:
    """
    Ensure a local, up-to-date clone of `github_url` exists on disk.

    - If no local clone exists yet, clones it fresh (full history - shallow
      clones would hide exactly the older commits we want to analyse).
    - If a clone already exists, fetches all refs and hard-resets to the
      remote's default branch.

    `fetch` + `reset` rather than `git pull` deliberately: this is a
    read-only mirror we re-derive data from, so a force-push upstream, a
    diverged local branch or a detached HEAD should not be able to fail the
    run with a merge conflict.

    Returns the local path to the repo's working directory.
    """
    dest = local_path_for(github_url)
    dest.parent.mkdir(parents=True, exist_ok=True)
    remote_url = _authenticated_url(github_url)

    if dest.exists() and (dest / ".git").exists():
        repo = git.Repo(dest)
        with repo.git.custom_environment(**_git_env()):
            # Fetch by passing the URL explicitly rather than via
            # `origin.set_url`, so a token-bearing URL is never written into
            # the clone's .git/config on disk.
            repo.git.fetch(
                remote_url, "+refs/heads/*:refs/remotes/origin/*", "--prune", "--tags"
            )
            repo.git.reset("--hard", _default_remote_ref(repo))
    else:
        repo = git.Repo.clone_from(remote_url, dest, env=_git_env())
        if remote_url != github_url:
            # `clone_from` records the URL it was given in .git/config, which
            # would leave the token sitting in a file on disk. Scrub it back
            # to the clean URL now that the clone has succeeded.
            repo.remotes.origin.set_url(github_url)

    return dest


def count_commits(repo_path: Path) -> int:
    """
    Count commits reachable from any ref, without the per-commit diff/stat
    work `commit_parser.parse_commits` does.

    Used right after a clone/fetch to decide whether a run is small enough
    to ingest inline or should be handed to a background task (see
    app.services.ingest_service.clone_and_count_commits) - a decision that
    needs to be cheap even on a repo with tens of thousands of commits.
    """
    repo = git.Repo(repo_path)
    return int(repo.git.rev_list("--all", "--count"))


def _default_remote_ref(repo: git.Repo) -> str:
    """
    Resolve the remote's default branch ref, e.g. "origin/main".

    Falls back through origin/HEAD -> origin/main -> origin/master -> the
    current local HEAD, so this keeps working on repos that use any of the
    common naming conventions.
    """
    try:
        # origin/HEAD is a symbolic ref pointing at the default branch.
        return repo.git.rev_parse("--abbrev-ref", "origin/HEAD").strip()
    except git.GitCommandError:
        pass

    for candidate in ("origin/main", "origin/master"):
        try:
            repo.git.rev_parse("--verify", candidate)
            return candidate
        except git.GitCommandError:
            continue

    return "HEAD"
