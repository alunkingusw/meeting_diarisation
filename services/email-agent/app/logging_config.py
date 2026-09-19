"""Structured logging setup. Never logs email bodies or attachment contents unless explicitly enabled."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from app.settings import Settings


def configure_logging(settings: Settings) -> None:
    level = getattr(logging, settings.logging.level.upper(), logging.INFO)
    settings.logging.log_dir.mkdir(parents=True, exist_ok=True)
    log_file = Path(settings.logging.log_dir) / "app.log"

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
