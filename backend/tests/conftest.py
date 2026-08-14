"""
Shared fixtures for the backend test suite.

Design notes (see the plan / README "Testing" section for the full rationale):

- API tests run against a real, disposable PostgreSQL container (via
  `testcontainers`), not SQLite, so Postgres-specific behaviour (JSON
  columns, native enums) is actually exercised.

- Importing `backend.main` pulls in the *entire* ML stack (whisper, torch,
  torchaudio, pyannote.audio, pyannote.core, scikit-learn) as a side effect,
  because `backend/routes/group_members.py` and `backend/routes/meetings.py`
  import `backend/processing/generate_embedding.py` and
  `backend/processing/transcribe.py` at module scope, and those import the ML
  libraries at module scope too. Dev machines that don't have the full
  CUDA/whisper/pyannote stack installed (this one included) would otherwise
  be unable to run even a plain CRUD test. `_stub_missing_module` installs a
  lightweight `MagicMock` stand-in for any of these that fail to import for
  real, so route/CRUD/auth logic can be exercised without them. Where the
  real packages ARE installed (e.g. inside the built Docker image), the
  stubs are skipped entirely and the real modules load normally.

- `backend/startup.py` no longer calls `Base.metadata.create_all()` (removed
  when the project switched to Alembic for schema management) - deployment
  now expects `alembic upgrade head` alone to build the schema from scratch.
  As of the "baseline schema" revision that isn't actually true: it's an
  `ALTER TABLE`-only migration that assumes the tables already exist, so
  `alembic upgrade head` against a genuinely empty database fails (see
  `backend/tests/test_migrations.py`, which fails on purpose to document
  this). Since that's a real bug rather than a test problem, this fixture
  works around it the same way the app used to: create the schema directly
  via `Base.metadata.create_all()`, then `alembic stamp head` to mark the DB
  as being at the latest revision, so route/CRUD/auth logic can still be
  exercised against a correct schema.
"""

import importlib
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import text
from testcontainers.community.postgres import PostgresContainer

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Modules that pull in the heavy/CUDA-specific ML stack. Stubbed only if the
# real package isn't importable in the current environment.
_STUBBABLE_MODULES = (
    "whisper",
    "torchaudio",
    "pyannote.audio",
    "pyannote.core",
    "sklearn.preprocessing",
    "sklearn.metrics.pairwise",
    "chromadb",
    "sentence_transformers",
)


def _stub_missing_module(dotted_name: str) -> None:
    parts = dotted_name.split(".")
    for i in range(1, len(parts) + 1):
        prefix = ".".join(parts[:i])
        if prefix in sys.modules:
            continue
        try:
            importlib.import_module(prefix)
            continue
        except ImportError:
            pass
        stub = MagicMock(name=prefix)
        sys.modules[prefix] = stub
        if i > 1:
            parent = sys.modules[".".join(parts[: i - 1])]
            setattr(parent, parts[i - 1], stub)


def _truncate_all_tables(engine) -> None:
    with engine.begin() as conn:
        tables = conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        ).scalars().all()
        tables = [t for t in tables if t != "alembic_version"]
        if tables:
            names = ", ".join(f'"{t}"' for t in tables)
            conn.execute(text(f"TRUNCATE TABLE {names} RESTART IDENTITY CASCADE"))


@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:15", username="test_user", password="test_pass", dbname="test_db") as pg:
        yield pg


@pytest.fixture(scope="session")
def app(postgres_container, tmp_path_factory):
    os.environ["POSTGRES_USER"] = postgres_container.username
    os.environ["POSTGRES_PASSWORD"] = postgres_container.password
    os.environ["POSTGRES_DB"] = postgres_container.dbname
    os.environ["POSTGRES_HOST"] = postgres_container.get_container_host_ip()
    os.environ["POSTGRES_PORT"] = str(postgres_container.get_exposed_port(5432))
    os.environ["SECRET_KEY"] = "test-secret-key"
    # Prefer a real, already-exported token (needed by the `integration`-marked
    # tests, which load real gated pyannote models) over the dummy placeholder.
    os.environ["HUGGING_FACE_TOKEN"] = os.environ.get("HUGGING_FACE_TOKEN", "test-dummy-token")
    os.environ["PGADMIN_DEFAULT_EMAIL"] = "test@example.com"
    os.environ["PGADMIN_DEFAULT_PASSWORD"] = "test-pass"
    os.environ["UPLOAD_DIR"] = str(tmp_path_factory.mktemp("uploads"))

    for name in _STUBBABLE_MODULES:
        _stub_missing_module(name)

    import backend.main as main_module

    from backend.db import Base, engine

    Base.metadata.create_all(bind=engine)

    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config(str(REPO_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    command.stamp(alembic_cfg, "head")

    return main_module.backend


@pytest.fixture(scope="session")
def db_engine(app):
    from backend.db import engine

    return engine


@pytest.fixture
def db_session(app, db_engine):
    from backend.db import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        _truncate_all_tables(db_engine)


@pytest.fixture
def client(app, db_session):
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_header_for(app):
    from backend.auth import create_token_for_user

    def _make(user_id: int) -> dict:
        return {"Authorization": f"Bearer {create_token_for_user(user_id)}"}

    return _make


@pytest.fixture
def make_user(db_session):
    from backend.models import User

    def _make(username="alice"):
        user = User(username=username)
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user

    return _make


@pytest.fixture
def make_group(db_session):
    from backend.models import Group

    def _make(name="Test Group", owner=None):
        group = Group(name=name)
        if owner is not None:
            group.users.append(owner)
        db_session.add(group)
        db_session.commit()
        db_session.refresh(group)
        return group

    return _make


@pytest.fixture
def make_member(db_session):
    from backend.models import GroupMember

    def _make(name="Bob", group=None):
        member = GroupMember(name=name)
        if group is not None:
            member.groups.append(group)
        db_session.add(member)
        db_session.commit()
        db_session.refresh(member)
        return member

    return _make


@pytest.fixture
def make_member_via_api(client, auth_header_for):
    """
    Like `make_member`, but goes through the real POST /groups/{id}/members/
    endpoint instead of inserting directly via SQLAlchemy. Use this instead
    of `make_member` whenever a test cares about creation-time side effects
    the route performs that a direct DB insert would bypass.
    """

    def _make(group, owner_id, name="Bob"):
        response = client.post(
            f"/groups/{group.id}/members/", json={"name": name}, headers=auth_header_for(owner_id)
        )
        assert response.status_code == 200, response.text
        return response.json()

    return _make


@pytest.fixture
def make_meeting(db_session):
    from datetime import datetime, timezone

    from backend.models import Meeting

    def _make(group, date=None):
        meeting = Meeting(group_id=group.id, date=date or datetime.now(timezone.utc))
        db_session.add(meeting)
        db_session.commit()
        db_session.refresh(meeting)
        return meeting

    return _make
