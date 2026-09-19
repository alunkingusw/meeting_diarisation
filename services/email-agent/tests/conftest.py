from pathlib import Path

import pytest

from app.storage.db import init_db


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "app.db"
    init_db(path)
    return path
