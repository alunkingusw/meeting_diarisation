"""Attachment persistence. The sender-provided filename is only ever used for display/matching
against the mail provider's real attachment list - the file is always stored under an
application-generated name, never the original, so it can never be used as a filesystem path
(spec S11)."""
from __future__ import annotations

import uuid
from pathlib import Path

from werkzeug.utils import secure_filename


def save_incoming(content: bytes, original_filename: str, incoming_dir: Path) -> Path:
    incoming_dir = Path(incoming_dir)
    incoming_dir.mkdir(parents=True, exist_ok=True)
    safe_name = secure_filename(original_filename) or "attachment"
    stored_name = f"{uuid.uuid4().hex}_{safe_name}"
    path = incoming_dir / stored_name
    path.write_bytes(content)
    return path


def move_to(path: Path, target_dir: Path) -> Path:
    """Moves a stored attachment to a different stage directory (processing/completed/failed),
    keeping its already-safe generated filename. Returns the new path."""
    path = Path(path)
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / path.name
    path.replace(dest)
    return dest
