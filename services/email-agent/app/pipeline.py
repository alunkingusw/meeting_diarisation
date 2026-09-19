"""Orchestrates one mail-poll cycle: fetch, authorise, parse via the LLM, validate, and dispatch
to the appropriate handler via an explicit if/elif over the finite operation set (spec S17) -
never a generic tool-call interface. Also flushes the Outbox (all outbound mail, including admin
alerts) through the MailClient.

This is the file that embodies the core architectural boundary from the spec:

    UNTRUSTED (email + LLM) -> Strict Validator -> TRUSTED (deterministic handlers)
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional, Protocol

from app.admin.notifier import AdminCategory, AdminNotifier
from app.auth.authorisation import AuthResultReason, SenderAuthoriser
from app.commands.schema import CommandParsingFailed, Operation
from app.commands.validator import (
    AttachmentMeta,
    ClarificationRequired,
    Rejected,
    ValidationContext,
    validate_command,
)
from app.email_templates.render import (
    render_clarification,
    render_clarification_received,
    render_failure,
    render_unrecognised_sender,
)
from app.handlers import assess_query as assess_query_handler
from app.handlers import add_comment as add_comment_handler
from app.handlers import cancel as cancel_handler
from app.handlers import help as help_handler
from app.handlers import results as results_handler
from app.handlers import status as status_handler
from app.handlers import submit_transcript
from app.jobs.store import JobStore, Outbox, PendingClarificationStore, ProcessedMessageStore
from app.jobs.models import JobState
from app.llm.command_parser import EmailCommandParser
from app.mail.base import EmailMessage, MailClient
from app.mail.thread_matcher import ThreadMatcher
from app.reports.reply import WeeklyReportReplyService
from app.reports.store import ReportStore
from app.settings import LimitsSettings, StorageSettings

logger = logging.getLogger(__name__)
WEEKLY_REPORT_ID_RE = re.compile(r"WEEKLY-\d{4}-\d{2}-\d{2}-\d{4}")


class HasIsAvailable(Protocol):
    def is_available(self) -> bool: ...


class EmailProcessingPipeline:
    def __init__(
        self,
        mail_client: MailClient,
        authoriser: SenderAuthoriser,
        ollama_client: HasIsAvailable,
        command_parser: EmailCommandParser,
        job_store: JobStore,
        processed_store: ProcessedMessageStore,
        outbox: Outbox,
        admin_notifier: AdminNotifier,
        thread_matcher: ThreadMatcher,
        storage: StorageSettings,
        limits: LimitsSettings,
        admin_email: Optional[str],
    ):
        self._mail = mail_client
        self._authoriser = authoriser
        self._ollama = ollama_client
        self._parser = command_parser
        self._job_store = job_store
        self._processed = processed_store
        self._outbox = outbox
        self._admin = admin_notifier
        self._thread_matcher = thread_matcher
        self._storage = storage
        self._limits = limits
        self._admin_email = admin_email
        self._pending_clarifications = PendingClarificationStore(job_store._db_path)
        self._report_store = ReportStore(job_store._db_path)
        self._report_replies = WeeklyReportReplyService(self._report_store, outbox, ollama_client)

    # --- inbound: fetch, authorise, parse, validate, dispatch ---------------------------------

    def poll_once(self) -> int:
        messages = self._mail.fetch_new_messages()
        for msg in messages:
            try:
                self._process_message(msg)
            except Exception:
                # A single malformed/unexpected message must never take down polling for
                # every other message in the batch.
                logger.exception("Unhandled error processing message %s", msg.message_id)
        return len(messages)

    def _process_message(self, msg: EmailMessage) -> None:
        auth_result = self._authoriser.authorise(msg.from_address, msg.auth_signals)
        dedup_sender = auth_result.sender_email or msg.from_address

        if not self._processed.begin(msg.message_id, dedup_sender, auth_result.reason.value):
            # Either already fully handled before (true duplicate) or its crash-recovery
            # retry budget is exhausted (see ProcessedMessageStore) - either way we're
            # definitively done with it, so it shouldn't keep resurfacing on future polls.
            logger.info("Skipping duplicate or exhausted message %s", msg.message_id)
            self._mail.mark_processed(msg.provider_ref)
            return

        if auth_result.reason == AuthResultReason.UNRECOGNISED_IN_DOMAIN:
            subject, body = render_unrecognised_sender(self._admin_email)
            self._outbox.enqueue(
                to_email=auth_result.sender_email,
                subject=subject,
                body_text=body,
                in_reply_to=msg.message_id,
                references=_reply_references(msg),
            )
            self._admin.alert(
                AdminCategory.UNAUTHORISED_SENDER,
                f"Unrecognised in-domain sender attempted to use the system: {auth_result.sender_email}",
            )
            self._processed.finalize(msg.message_id, outcome="unrecognised_sender_replied")
            self._mail.mark_processed(msg.provider_ref)
            return

        if auth_result.reason != AuthResultReason.AUTHORISED:
            # unauthorised_external / unauthenticated / malformed_sender - silent drop, no
            # reply (spec decision: replying would confirm a monitored mailbox exists).
            self._admin.alert(
                AdminCategory.UNAUTHORISED_SENDER,
                f"Rejected sender ({auth_result.reason.value}): {msg.from_address}",
            )
            self._processed.finalize(msg.message_id, outcome="rejected_silently")
            self._mail.mark_processed(msg.provider_ref)
            return

        sender_email = auth_result.sender_email
        sender_user_id = auth_result.user_id
        report = self._match_report(msg, sender_email)
        if report is not None:
            if not self._ollama.is_available():
                logger.warning("Ollama unavailable - deferring weekly report reply %s", msg.message_id)
                return
            self._report_replies.reply(msg, report.report_id)
            self._processed.finalize(
                msg.message_id, outcome="weekly_report_reply", job_id=report.report_id,
                operation="weekly_report_reply",
            )
            self._mail.mark_processed(msg.provider_ref)
            return
        thread_job_id = self._thread_matcher.match(msg, sender_email)

        if thread_job_id and self._continue_clarification(msg, sender_email, thread_job_id):
            return

        if not self._ollama.is_available():
            # Deliberately do NOT finalize or mark_processed: the message stays 'in_progress'
            # in our ledger and unread on the provider, so it's retried on a later poll once
            # Ollama comes back (spec S20: "do not process the command; leave the email
            # available for later retry").
            logger.warning("Ollama unavailable - deferring message %s", msg.message_id)
            self._admin.alert(AdminCategory.INFRASTRUCTURE, "Ollama is unreachable")
            return

        attachment_filenames = [a.filename for a in msg.attachments]

        try:
            parsed_cmd = self._parser.parse_email(
                msg.body_text, attachment_filenames, thread_job_id, subject=msg.subject
            )
        except CommandParsingFailed as e:
            self._reply_and_finalize(
                msg,
                *render_clarification(
                    "I couldn't understand your request. Could you rephrase it, mentioning "
                    "clearly what you'd like me to do (submit a transcript, check status, see "
                    "results, or cancel a request)?"
                ),
                outcome="llm_parse_failed",
            )
            self._admin.alert(
                AdminCategory.LLM_PARSE_FAILURE, f"Could not parse email from {sender_email}: {e}"
            )
            return

        attachments_meta = [
            AttachmentMeta(a.filename, a.size_bytes, a.content_type) for a in msg.attachments
        ]
        ctx = ValidationContext(
            attachments=attachments_meta,
            thread_job_id=thread_job_id,
            sender_email=sender_email,
            job_store=self._job_store,
            limits=self._limits,
            subject=msg.subject,
        )

        try:
            validated = validate_command(parsed_cmd, ctx)
        except ClarificationRequired as e:
            self._reply_and_finalize(
                msg, *render_clarification(e.question, thread_job_id), outcome="clarification_sent",
                operation=parsed_cmd.operation.value,
            )
            return
        except Rejected as e:
            self._reply_and_finalize(
                msg, *render_failure(str(e), thread_job_id), outcome="rejected", operation=parsed_cmd.operation.value,
            )
            return

        try:
            job_id = self._dispatch(
                validated, msg, sender_email, sender_user_id,
                msg.message_id, _reply_references(msg),
            )
        except ClarificationRequired as e:
            self._reply_and_finalize(
                msg, *render_clarification(e.question, thread_job_id), outcome="clarification_sent",
                operation=validated.operation.value,
            )
            return
        except Rejected as e:
            self._reply_and_finalize(
                msg, *render_failure(str(e), thread_job_id), outcome="rejected", operation=validated.operation.value,
            )
            return

        self._processed.finalize(
            msg.message_id, outcome="handled", job_id=job_id, operation=validated.operation.value
        )
        self._mail.mark_processed(msg.provider_ref)

    def _dispatch(
        self, validated, msg: EmailMessage, sender_email: str, sender_user_id: int,
        in_reply_to: str, references: str,
    ) -> Optional[str]:
        """The explicit, finite dispatch (spec S17) - deliberately not a generic
        operation-name-to-callable lookup, so the full set of possible actions is visible here."""
        if validated.operation == Operation.SUBMIT_TRANSCRIPT:
            outcome = submit_transcript.accept(
                msg.attachments,
                validated,
                sender_email,
                sender_user_id,
                msg.message_id,
                msg.received_at,
                self._job_store,
                self._outbox,
                self._storage,
                in_reply_to,
                references,
            )
        elif validated.operation == Operation.STATUS:
            outcome = status_handler.handle(
                validated, sender_email, self._job_store, self._outbox, in_reply_to, references
            )
        elif validated.operation == Operation.RESULTS:
            outcome = results_handler.handle(
                validated, sender_email, self._job_store, self._outbox, in_reply_to, references
            )
        elif validated.operation == Operation.CANCEL:
            outcome = cancel_handler.handle(
                validated, sender_email, self._job_store, self._outbox, in_reply_to, references
            )
        elif validated.operation == Operation.ASSESS_QUERY:
            outcome = assess_query_handler.accept(
                validated, sender_email, sender_user_id, msg.message_id, self._job_store,
                self._outbox, in_reply_to, references,
            )
        elif validated.operation == Operation.ADD_COMMENT:
            outcome = add_comment_handler.accept(
                validated, sender_email, sender_user_id, msg.message_id, self._job_store,
                self._outbox, in_reply_to, references,
            )
        elif validated.operation == Operation.HELP:
            outcome = help_handler.handle(sender_email, self._outbox, in_reply_to, references)
        else:
            raise Rejected(f"Unsupported operation: {validated.operation!r}")  # unreachable
        return outcome.job_id

    def _continue_clarification(self, msg: EmailMessage, sender_email: str, job_id: str) -> bool:
        pending = self._pending_clarifications.get(job_id)
        if pending is None:
            return False

        answer = _first_unquoted_line(msg.body_text)
        matches = [option for option in pending.options if _normalise(option) == _normalise(answer)]
        if len(matches) != 1:
            subject, body = render_clarification(pending.question, job_id)
            self._outbox.enqueue(
                to_email=sender_email,
                subject=subject,
                body_text=body,
                job_id=job_id,
                in_reply_to=msg.message_id,
                references=_reply_references(msg),
            )
            self._processed.finalize(msg.message_id, outcome="clarification_sent", operation="clarification")
            self._mail.mark_processed(msg.provider_ref)
            return True

        job = self._job_store.get_owned(job_id, sender_email)
        if job is None or job.status.value != "NEEDS_CLARIFICATION":
            return False

        selected = matches[0]
        self._job_store.update(job_id, group_hint=selected, in_reply_to_message_id=msg.message_id)
        self._job_store.set_status(job_id, JobState.QUEUED)
        self._pending_clarifications.delete(job_id)
        subject, body = render_clarification_received(job_id, selected)
        self._outbox.enqueue(
            to_email=sender_email,
            subject=subject,
            body_text=body,
            job_id=job_id,
            in_reply_to=msg.message_id,
            references=_reply_references(msg),
        )
        self._processed.finalize(msg.message_id, outcome="clarification_applied", job_id=job_id, operation="clarification")
        self._mail.mark_processed(msg.provider_ref)
        return True

    def _match_report(self, msg: EmailMessage, sender_email: str):
        for message_id in (f"{msg.in_reply_to or ''} {msg.references or ''}").split():
            report = self._report_store.get_by_message_id(message_id, sender_email)
            if report is not None:
                return report
        for report_id in WEEKLY_REPORT_ID_RE.findall(
            f"{msg.subject or ''} {msg.body_text or ''}"
        ):
            report = self._report_store.get(report_id)
            if report and report.owner_email.casefold() == sender_email.casefold():
                return report
        return None

    def _reply_and_finalize(
        self, msg: EmailMessage, subject: str, body: str, outcome: str, operation: Optional[str] = None
    ) -> None:
        self._outbox.enqueue(
            to_email=msg.from_address,
            subject=subject,
            body_text=body,
            in_reply_to=msg.message_id,
            references=_reply_references(msg),
        )
        self._processed.finalize(msg.message_id, outcome=outcome, operation=operation)
        self._mail.mark_processed(msg.provider_ref)

    # --- outbound: flush queued mail through the provider --------------------------------------

    def flush_outbox(self) -> int:
        sent = 0
        for message in self._outbox.pending():
            try:
                attachments = (
                    [(Path(p).name, Path(p).read_bytes()) for p in message.attachments]
                    if message.attachments
                    else None
                )
                provider_message_id = self._mail.send_email(
                    to=message.to_email,
                    subject=message.subject,
                    body_text=message.body_text,
                    attachments=attachments,
                    in_reply_to=message.in_reply_to_message_id,
                    references=message.references_header,
                )
                self._outbox.mark_sent(message.id, provider_message_id)
                if message.job_id:
                    self._job_store.update(message.job_id, last_response_message_id=provider_message_id)
                sent += 1
            except Exception as e:
                logger.exception("Failed to send outbox message %s", message.id)
                self._outbox.mark_failed(message.id, str(e))
        return sent


def _reply_references(msg: EmailMessage) -> str:
    values = [msg.references, msg.in_reply_to, msg.message_id]
    return " ".join(dict.fromkeys(value for value in values if value))


def _normalise(value: str) -> str:
    return " ".join((value or "").strip().casefold().split())


def _first_unquoted_line(body: str) -> str:
    for line in (body or "").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith(">"):
            return stripped
    return ""
