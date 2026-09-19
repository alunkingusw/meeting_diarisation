"""Renders outbound email subject/body text.

Wording is plain-language and never exposes internal operation names to the sender (e.g. "your
transcript" rather than "your submit_transcript request") - see spec S15's example emails, which
this is adapted from.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader

_TEMPLATE_DIR = Path(__file__).parent / "text"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=False,  # plain-text email bodies, not HTML
    trim_blocks=True,
    lstrip_blocks=True,
)


def _render(name: str, **kwargs) -> str:
    return _env.get_template(name).render(**kwargs).strip() + "\n"


def render_ack(job_id: str, filename: str, meeting_date: str, group_name: Optional[str]) -> tuple[str, str]:
    subject = f"Transcript received — {job_id}"
    body = _render(
        "ack.txt.j2", job_id=job_id, filename=filename, meeting_date=meeting_date, group_name=group_name
    )
    return subject, body


def render_clarification(question: str, job_id: Optional[str] = None) -> tuple[str, str]:
    subject = f"Clarification needed — {job_id}" if job_id else "Clarification needed"
    body = _render("clarification.txt.j2", question=question)
    return subject, body


def render_clarification_received(job_id: str, value: str) -> tuple[str, str]:
    subject = f"Clarification received — {job_id}"
    body = f"Thanks. I recorded '{value}' for {job_id} and queued it to continue processing.\n"
    return subject, body


def render_failure(reason: str, job_id: Optional[str] = None) -> tuple[str, str]:
    subject = f"Could not process your request — {job_id}" if job_id else "Could not process your request"
    body = _render("failure.txt.j2", job_id=job_id, reason=reason)
    return subject, body


def render_completion(
    job_id: str,
    group_name: str,
    meeting_date: str,
    resolved_attendees: list[str],
    unresolved_speakers: list[str],
) -> tuple[str, str]:
    subject = f"Transcript processed — {job_id}"
    body = _render(
        "completion.txt.j2",
        job_id=job_id,
        group_name=group_name,
        meeting_date=meeting_date,
        resolved_attendees=resolved_attendees,
        unresolved_speakers=unresolved_speakers,
    )
    return subject, body


def render_status(job_id: str, status_text: str) -> tuple[str, str]:
    subject = f"Status of {job_id}"
    body = _render("status.txt.j2", job_id=job_id, status_text=status_text)
    return subject, body


def render_results(
    job_id: str,
    status_text: str,
    group_name: Optional[str] = None,
    meeting_date: Optional[str] = None,
    resolved_attendees: Optional[list[str]] = None,
    unresolved_speakers: Optional[list[str]] = None,
) -> tuple[str, str]:
    subject = f"Results for {job_id}"
    body = _render(
        "results.txt.j2",
        job_id=job_id,
        status_text=status_text,
        group_name=group_name,
        meeting_date=meeting_date,
        resolved_attendees=resolved_attendees or [],
        unresolved_speakers=unresolved_speakers or [],
    )
    return subject, body


def render_cancelled(job_id: str) -> tuple[str, str]:
    subject = f"Cancelled — {job_id}"
    body = _render("cancelled.txt.j2", job_id=job_id)
    return subject, body


def render_cannot_cancel(job_id: str, status_text: str) -> tuple[str, str]:
    subject = f"Could not cancel — {job_id}"
    body = _render("cannot_cancel.txt.j2", job_id=job_id, status_text=status_text)
    return subject, body


def render_assess_ack(job_id: str) -> tuple[str, str]:
    subject = f"Looking into your question — {job_id}"
    body = _render("assess_ack.txt.j2", job_id=job_id)
    return subject, body


def render_comment_confirmation(job_id: str, result) -> tuple[str, str]:
    subject = f"Comment added - {job_id}"
    body = _render("comment_confirmation.txt.j2", job_id=job_id, result=result)
    return subject, body


def render_assess_result(
    job_id: str,
    group_name: Optional[str],
    transcript_answer: Optional[str],
    github_trello_answer: Optional[str],
    trello_checked: bool,
    unavailable_notes: list[str],
) -> tuple[str, str]:
    subject = f"Here's what I found — {job_id}"
    body = _render(
        "assess_result.txt.j2",
        job_id=job_id,
        group_name=group_name,
        transcript_answer=transcript_answer,
        github_trello_answer=github_trello_answer,
        trello_checked=trello_checked,
        unavailable_notes=unavailable_notes,
    )
    return subject, body


def render_help() -> tuple[str, str]:
    subject = "What can I ask this system to do?"
    body = _render("help.txt.j2")
    return subject, body


def render_unrecognised_sender(admin_email: Optional[str]) -> tuple[str, str]:
    subject = "You're not currently registered to use this system"
    body = _render("unrecognised_sender.txt.j2", admin_email=admin_email)
    return subject, body
