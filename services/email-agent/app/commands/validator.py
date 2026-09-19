"""Trust boundary #1: turns an LLM-produced ParsedCommand into a ValidatedCommand.

Nothing here trusts the LLM's output just because it parsed as valid JSON/schema. Every field
that matters for *what actually happens* (which attachment, which job) is re-resolved against
real, deterministic sources - the mail provider's actual attachment list, and our own job store
- never taken at face value from the model. Ambiguity always raises ClarificationRequired rather
than guessing (the "be conservative" product requirement); genuinely invalid input (wrong file
type, oversized, unknown job) raises Rejected.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from app.commands.schema import Operation, ParsedCommand

if TYPE_CHECKING:
    from app.jobs.store import JobStore
    from app.settings import LimitsSettings

_ALLOWED_OPERATIONS = frozenset(Operation)

# Used only to give a specific "audio isn't accepted" message rather than a generic
# "unsupported file type" one - not a security control (the .vtt-only check below is).
_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".aac", ".wma"}


class Rejected(Exception):
    """Deterministic hard rejection - invalid input, not ambiguity. Becomes a plain
    'failure' reply to the sender; never triggers an admin alert on its own (spec: don't
    alert the admin for ordinary user mistakes)."""


class ClarificationRequired(Exception):
    """The named conservative pattern: real ambiguity that could result in acting on the
    wrong data. Always becomes a clarification email to the sender, never a guess."""

    def __init__(self, question: str):
        super().__init__(question)
        self.question = question


@dataclass
class AttachmentMeta:
    filename: str
    size_bytes: int
    content_type: str


@dataclass
class ValidationContext:
    attachments: list[AttachmentMeta]
    thread_job_id: Optional[str]
    sender_email: str
    job_store: "JobStore"
    limits: "LimitsSettings"
    subject: str = ""


@dataclass
class ValidatedCommand:
    operation: Operation
    attachment: Optional[AttachmentMeta] = None
    group_hint: Optional[str] = None
    mentioned_date: Optional[str] = None
    job_id: Optional[str] = None
    return_statistics: bool = False
    transcript_focus: Optional[str] = None
    github_focus: Optional[str] = None
    trello_focus: Optional[str] = None
    comment: Optional[str] = None
    group_id: Optional[int] = None
    meeting_id: Optional[int] = None


def validate_command(cmd: ParsedCommand, ctx: ValidationContext) -> ValidatedCommand:
    if cmd.operation not in _ALLOWED_OPERATIONS:
        # Unreachable in practice (ParsedCommand.operation is already a validated Operation
        # enum member) - kept as an explicit belt-and-braces check on the finite command set.
        raise Rejected(f"Unsupported operation: {cmd.operation!r}")

    if cmd.requires_clarification:
        raise ClarificationRequired(
            cmd.clarification_question or "Could you clarify what you'd like me to do?"
        )

    if cmd.operation == Operation.SUBMIT_TRANSCRIPT:
        return _validate_submit_transcript(cmd, ctx)
    if cmd.operation in (Operation.STATUS, Operation.RESULTS, Operation.CANCEL):
        return _validate_job_reference_operation(cmd, ctx)
    if cmd.operation == Operation.ASSESS_QUERY:
        return _validate_assess_query(cmd, ctx)
    if cmd.operation == Operation.ADD_COMMENT:
        return _validate_add_comment(cmd, ctx)
    if cmd.operation == Operation.HELP:
        return ValidatedCommand(operation=Operation.HELP)

    raise Rejected(f"Unsupported operation: {cmd.operation!r}")  # unreachable


def _validate_submit_transcript(cmd: ParsedCommand, ctx: ValidationContext) -> ValidatedCommand:
    if not ctx.attachments:
        raise ClarificationRequired(
            "I didn't find any attachment on your email. Please resend with a .vtt transcript "
            "attached."
        )

    vtt_candidates = [a for a in ctx.attachments if a.filename.lower().endswith(".vtt")]

    # The LLM's `attachment` field is only ever used as a lookup key against the mail
    # provider's *real* attachment list - never trusted as a path or as proof of file type.
    matched = None
    if cmd.attachment:
        matched = next((a for a in ctx.attachments if a.filename == cmd.attachment), None)

    if matched is None:
        if len(vtt_candidates) == 1:
            matched = vtt_candidates[0]
        elif len(vtt_candidates) == 0:
            audio_candidates = [a for a in ctx.attachments if _is_audio(a.filename)]
            if audio_candidates:
                raise Rejected(
                    "Audio attachments aren't accepted by email. Please ask the admin to add "
                    "audio directly, or send an already-produced .vtt transcript instead."
                )
            raise ClarificationRequired(
                "I couldn't find a .vtt transcript attached. Only .vtt files are accepted by "
                "email - could you resend with one attached?"
            )
        else:
            names = ", ".join(a.filename for a in vtt_candidates)
            raise ClarificationRequired(
                f"I found multiple .vtt attachments ({names}) and wasn't sure which one you "
                "meant. Could you resend mentioning just the one file, or send them separately?"
            )

    # Re-check the *actually resolved* attachment's real properties - never the LLM's claim.
    if _is_audio(matched.filename):
        raise Rejected(
            "Audio attachments aren't accepted by email. Please ask the admin to add audio "
            "directly, or send an already-produced .vtt transcript instead."
        )
    if not matched.filename.lower().endswith(".vtt"):
        raise Rejected(
            f"'{matched.filename}' isn't a supported attachment type. Only .vtt transcripts "
            "are accepted by email."
        )

    max_bytes = int(ctx.limits.max_attachment_size_mb * 1024 * 1024)
    if matched.size_bytes > max_bytes:
        raise Rejected(
            f"'{matched.filename}' is too large "
            f"({matched.size_bytes / (1024 * 1024):.1f} MB). The maximum accepted size is "
            f"{ctx.limits.max_attachment_size_mb:.0f} MB."
        )

    return ValidatedCommand(
        operation=Operation.SUBMIT_TRANSCRIPT,
        attachment=matched,
        group_hint=cmd.group_hint,
        mentioned_date=cmd.mentioned_date,
    )


def _validate_job_reference_operation(
    cmd: ParsedCommand, ctx: ValidationContext
) -> ValidatedCommand:
    job_id = cmd.job_id or ctx.thread_job_id
    if not job_id:
        raise ClarificationRequired(
            "Which job did you mean? Please include the job ID (e.g. DIAR-2026-0811-0017), or "
            "reply directly on the email thread for that job."
        )

    job = ctx.job_store.get_owned(job_id, ctx.sender_email)
    if job is None:
        # Deliberately the same message whether the job doesn't exist or belongs to someone
        # else - never confirms/denies another sender's job exists.
        raise ClarificationRequired(
            f"I couldn't find a job {job_id} associated with your account. Please double-check "
            "the job ID."
        )

    return ValidatedCommand(
        operation=cmd.operation,
        job_id=job_id,
        return_statistics=cmd.return_statistics,
    )


def _validate_assess_query(cmd: ParsedCommand, ctx: ValidationContext) -> ValidatedCommand:
    if not (cmd.transcript_focus or cmd.github_focus or cmd.trello_focus):
        raise ClarificationRequired(
            "I couldn't tell whether this needs checking against meeting transcripts, the "
            "GitHub repo, the Trello board, or some combination - could you say a bit more "
            "about what you're trying to find out?"
        )
    return ValidatedCommand(
        operation=Operation.ASSESS_QUERY,
        group_hint=cmd.group_hint,
        transcript_focus=cmd.transcript_focus,
        github_focus=cmd.github_focus,
        trello_focus=cmd.trello_focus,
    )


def _validate_add_comment(cmd: ParsedCommand, ctx: ValidationContext) -> ValidatedCommand:
    group_match = re.search(r"\bgroup_id=(\d+)\b", ctx.subject, re.IGNORECASE)
    meeting_match = re.search(r"\bmeeting_id=(\d+)\b", ctx.subject, re.IGNORECASE)
    if not group_match or not meeting_match:
        raise ClarificationRequired(
            "Please reply with both group_id=<number> and meeting_id=<number> in the subject."
        )
    if not cmd.comment:
        raise ClarificationRequired("What text would you like me to add as the meeting comment?")
    return ValidatedCommand(
        operation=Operation.ADD_COMMENT,
        group_id=int(group_match.group(1)),
        meeting_id=int(meeting_match.group(1)),
        comment=cmd.comment,
    )


def _is_audio(filename: str) -> bool:
    lower = filename.lower()
    return any(lower.endswith(ext) for ext in _AUDIO_EXTENSIONS)
