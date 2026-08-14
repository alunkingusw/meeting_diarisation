"""
Checks that Alembic's migration history can actually build the schema on a
brand new database, independent of `backend/tests/conftest.py`'s bootstrap
(which deliberately mirrors how the app has *actually* always been
bootstrapped: `Base.metadata.create_all()` followed by `alembic stamp head`).

This test uses its own throwaway Postgres container - not the shared one
from conftest.py - specifically so nothing has run `Base.metadata.create_all()`
against it first.
"""

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from testcontainers.community.postgres import PostgresContainer

REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_KEYS = ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "POSTGRES_HOST", "POSTGRES_PORT")


def test_alembic_upgrade_head_builds_schema_from_scratch():
    """
    docker-compose.yml boots the API container with
    `alembic upgrade head && uvicorn ...`, which implies migrations alone
    should be able to build the full schema on a brand new database (e.g. a
    fresh volume on first deploy). This test runs `alembic upgrade head`
    against a genuinely empty Postgres to check that assumption holds.
    """
    saved_env = {key: os.environ.get(key) for key in _ENV_KEYS}
    try:
        with PostgresContainer(
            "postgres:15", username="migrate_user", password="migrate_pass", dbname="migrate_db"
        ) as pg:
            os.environ["POSTGRES_USER"] = pg.username
            os.environ["POSTGRES_PASSWORD"] = pg.password
            os.environ["POSTGRES_DB"] = pg.dbname
            os.environ["POSTGRES_HOST"] = pg.get_container_host_ip()
            os.environ["POSTGRES_PORT"] = str(pg.get_exposed_port(5432))

            alembic_cfg = Config(str(REPO_ROOT / "alembic.ini"))
            alembic_cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))

            command.upgrade(alembic_cfg, "head")

            # Round-trip: downgrading all the way back to base and upgrading
            # again should also work cleanly (exercises every downgrade()).
            command.downgrade(alembic_cfg, "base")
            command.upgrade(alembic_cfg, "head")
    finally:
        for key, value in saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
