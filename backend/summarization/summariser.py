# Copyright 2025 Alun King
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Generates a meeting summary via the local Ollama LLM (backend/llm) from
whichever transcript .vtt is on disk for the meeting, and caches the result
on Meeting.summary (see backend/routes/meetings.py's /summarise endpoint).

Two call sites feed this automatically, same split as transcript indexing
(backend/transcript_rag/indexer.py): a directly-uploaded .vtt
(backend/routes/upload.py) and a server-transcribed one
(backend/processing/transcribe.py).
"""

import logging
from datetime import datetime
from pathlib import Path
from string import Template

from sqlalchemy.orm import Session

from backend.config import settings
from backend.email_client import EmailError, send_email
from backend.llm.ollama_client import OllamaClient
from backend.models import Group, Meeting, RawFile, RawFileType
from backend.transcript_rag.vtt_rag.chunker import merge_cues_into_turns
from backend.transcript_rag.vtt_rag.parsing import parse_vtt_cues

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You summarise meeting transcripts for a project team. Write a concise summary "
    "covering the key discussion points, any decisions made, and any action items "
    "(including who owns them, if stated). Only use information present in the "
    "transcript - do not invent names, dates, or outcomes."
)
EMAIL_TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "templates" / "meeting_summary_email.txt"


def _latest_transcript_file(db: Session, meeting_id: int) -> RawFile:
    transcript = (
        db.query(RawFile)
        .filter(
            RawFile.meeting_id == meeting_id,
            RawFile.type.in_([RawFileType.TRANSCRIPT_PROVIDED, RawFileType.TRANSCRIPT_GENERATED]),
        )
        .order_by(RawFile.id.desc())
        .first()
    )
    if not transcript:
        raise FileNotFoundError(f"No transcript found for meeting {meeting_id}")
    return transcript


def _transcript_text(group_id: int, meeting_id: int, transcript: RawFile) -> str:
    vtt_path = settings.UPLOAD_DIR / str(group_id) / str(meeting_id) / transcript.file_name
    if not vtt_path.exists():
        raise FileNotFoundError(f"Transcript file missing on disk: {vtt_path}")

    raw_text = vtt_path.read_text(encoding="utf-8", errors="replace")
    turns = merge_cues_into_turns(parse_vtt_cues(raw_text))
    return "\n\n".join(f"{turn.speaker}: {turn.text}" for turn in turns)


def _render_summary_email(group: Group, meeting: Meeting, summary: str) -> tuple[str, str]:
    template_lines = EMAIL_TEMPLATE_PATH.read_text(encoding="utf-8").splitlines()
    template_text = "\n".join(line for line in template_lines if not line.startswith("#"))
    body = Template(template_text).substitute(
        group_name=group.name or "Unnamed group",
        meeting_date=meeting.date.date().isoformat(),
        meeting_id=meeting.id,
        summary=summary,
    )
    subject = (
        f"Meeting summary: {group.name or 'Unnamed group'} "
        f"[group_id={group.id}, meeting_id={meeting.id}]"
    )
    return subject, body.strip()


def _send_summary_notifications(group: Group, meeting: Meeting, summary: str) -> None:
    if not group.notify:
        return

    recipients = list(dict.fromkeys(
        member.email.strip()
        for member in group.members
        if member.email and member.email.strip()
    ))
    if not recipients:
        logger.info("Notifications enabled but no member email addresses exist for group %s", group.id)
        return

    try:
        subject, body = _render_summary_email(group, meeting, summary)
    except Exception:
        logger.exception("Could not render summary email for meeting %s", meeting.id)
        return

    for recipient in recipients:
        try:
            send_email(to=recipient, subject=subject, body=body)
        except EmailError:
            logger.exception("Could not send summary email for meeting %s to %s", meeting.id, recipient)


def generate_meeting_summary(db: Session, group: Group, meeting: Meeting) -> str:
    """Summarise `meeting`'s latest transcript and store it on the Meeting row.

    Raises FileNotFoundError if no transcript is available yet, or
    backend.llm.ollama_client.OllamaError if the local LLM call fails - callers
    decide whether that should fail the request (the /summarise endpoint) or
    just be logged (the automatic pipeline call, see summarise_meeting_task).
    """
    transcript = _latest_transcript_file(db, meeting.id)
    transcript_text = _transcript_text(group.id, meeting.id, transcript)

    user_prompt = (
        f"Meeting: {group.name}\n"
        f"Date: {meeting.date.date().isoformat()}\n\n"
        f"Transcript:\n{transcript_text}"
    )

    with OllamaClient() as llm:
        answer = llm.chat(system_prompt=SYSTEM_PROMPT, user_prompt=user_prompt)

    meeting.summary = answer.text
    meeting.summary_generated_at = datetime.now().astimezone()
    db.commit()
    db.refresh(meeting)

    logger.info("Generated summary for meeting %s (group %s)", meeting.id, group.id)
    _send_summary_notifications(group, meeting, meeting.summary)
    return meeting.summary


def summarise_meeting_task(group_id: int, meeting_id: int, db: Session) -> None:
    """Non-fatal wrapper for the upload/transcribe pipeline - same treatment as
    transcript indexing (see backend/transcript_rag/indexer.py's call sites):
    the transcript itself already succeeded, so a summarisation failure here is
    logged rather than raised."""
    group = db.query(Group).get(group_id)
    meeting = db.query(Meeting).get(meeting_id)
    if not group or not meeting:
        logger.warning("Skipping auto-summarisation: group %s or meeting %s not found", group_id, meeting_id)
        return

    try:
        generate_meeting_summary(db, group, meeting)
    except Exception:
        logger.exception("Automatic summarisation failed for meeting %s", meeting_id)
