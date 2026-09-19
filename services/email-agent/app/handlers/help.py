from __future__ import annotations

from app.email_templates.render import render_help
from app.handlers.base import HandlerOutcome
from app.jobs.store import Outbox


def handle(sender_email: str, outbox: Outbox, in_reply_to: str | None = None,
           references: str | None = None) -> HandlerOutcome:
    subject, body = render_help()
    outbox.enqueue(
        to_email=sender_email, subject=subject, body_text=body,
        in_reply_to=in_reply_to, references=references,
    )
    return HandlerOutcome("help_reply")
