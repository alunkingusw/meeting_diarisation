"""Entry point: wires all components together and runs the mail-polling pipeline and the job
worker as two threads sharing the same SQLite-backed stores, until interrupted."""
from __future__ import annotations

import logging
import signal
import threading
import time

from app.admin.notifier import AdminNotifier
from app.auth.authorisation import SenderAuthoriser
from app.diarisation.admin_client import AdminDiarisationApiError, AdminDiarisationClient
from app.diarisation.client import DiarisationClient
from app.jobs.store import JobStore, Outbox, ProcessedMessageStore
from app.jobs.worker import JobWorker
from app.internal_api import EmailApiServer
from app.llm.command_parser import EmailCommandParser
from app.llm.ollama_client import OllamaClient
from app.logging_config import configure_logging
from app.mail.base import MailClient
from app.mail.fake_client import FakeMailClient
from app.mail.imap_client import ImapMailClient
from app.mail.graph_client import GraphMailClient
from app.mail.thread_matcher import ThreadMatcher
from app.meeting_reports import run_scheduler
from app.pipeline import EmailProcessingPipeline
from app.settings import Settings, load_settings
from app.storage.db import init_db

logger = logging.getLogger(__name__)


def build_mail_client(settings: Settings) -> MailClient:
    if settings.mail.provider == "graph":
        if not (settings.graph_tenant_id and settings.graph_client_id and settings.graph_client_secret):
            raise RuntimeError(
                "mail.provider is 'graph' but GRAPH_TENANT_ID/GRAPH_CLIENT_ID/GRAPH_CLIENT_SECRET "
                "are not all set in .env"
            )
        return GraphMailClient(
            settings.graph_tenant_id,
            settings.graph_client_id,
            settings.graph_client_secret,
            settings.mail.mailbox_upn,
        )
    if settings.mail.provider == "mail":
        if not (settings.mail_username and settings.mail_password):
            raise RuntimeError(
                "mail.provider is 'mail' but MAIL_USERNAME and MAIL_PASSWORD must both be set in .env"
            )
        return ImapMailClient(
            settings.mail_username,
            settings.mail_password,
        )
    if settings.mail.provider == "fake":
        return FakeMailClient()
    raise RuntimeError(
        f"Unsupported mail.provider {settings.mail.provider!r} - only 'graph', 'mail', and 'fake' are "
        "currently implemented."
    )


def load_group_owners(settings: Settings) -> dict[str, int]:
    """Authorised sender emails now come live from meeting_diarisation's /admin/group-owners
    (backend/routes/admin.py there) rather than a static map. `authorisation.group_owners` in
    config.yaml is kept as an explicit override for tests/the fake mail-provider dev loop, which
    shouldn't need a live backend - if it's set, it wins outright and the backend is never
    called. Otherwise, a failure to reach the backend (or no service key configured) logs a
    warning and starts with an empty map - authorising nobody - rather than crash-looping,
    matching this project's "be conservative, never guess" pattern (see app/auth/authorisation.py)."""
    if settings.authorisation.group_owners:
        return settings.authorisation.group_owners

    if not settings.diarisation_service_api_key:
        logger.warning(
            "No DIARISATION_SERVICE_API_KEY set and no static authorisation.group_owners "
            "override in config.yaml - starting with no authorised senders."
        )
        return {}

    with AdminDiarisationClient(
        settings.backend.base_url,
        settings.diarisation_service_api_key,
        settings.backend.request_timeout_seconds,
    ) as admin_client:
        try:
            return admin_client.get_group_owners()
        except AdminDiarisationApiError:
            logger.exception(
                "Could not fetch group-owners from meeting_diarisation at startup - "
                "starting with no authorised senders."
            )
            return {}


def load_group_members(settings: Settings) -> dict[str, list[int]]:
    if not settings.diarisation_service_api_key:
        return {}

    with AdminDiarisationClient(
        settings.backend.base_url,
        settings.diarisation_service_api_key,
        settings.backend.request_timeout_seconds,
    ) as admin_client:
        try:
            return admin_client.get_group_members()
        except AdminDiarisationApiError:
            logger.exception(
                "Could not fetch group-member emails from meeting_diarisation - "
                "starting without GroupMember email authorization."
            )
            return {}


def run(settings: Settings) -> None:
    settings.ensure_storage_dirs()
    configure_logging(settings)
    init_db(settings.storage.db_path)

    mail_client = build_mail_client(settings)
    job_store = JobStore(settings.storage.db_path)
    processed_store = ProcessedMessageStore(settings.storage.db_path)
    outbox = Outbox(settings.storage.db_path)
    admin_notifier = AdminNotifier(
        settings.storage.db_path, outbox, settings.admin_email, settings.admin.alert_cooldown_minutes
    )
    authoriser = SenderAuthoriser(
        load_group_owners(settings),
        settings.authorisation.require_auth_pass,
        group_members=load_group_members(settings),
    )
    ollama_client = OllamaClient(
        settings.llm.host, settings.llm.model, settings.llm.request_timeout_seconds
    )
    command_parser = EmailCommandParser(
        ollama_client, settings.llm.max_parse_retries, settings.limits.max_email_body_chars
    )
    thread_matcher = ThreadMatcher(job_store)
    diarisation_client = DiarisationClient(
        settings.backend.base_url,
        settings.backend.request_timeout_seconds,
        settings.backend.max_retry_attempts,
        settings.backend.retry_backoff_seconds,
        settings.diarisation_service_api_key,
        settings.backend.query_timeout_seconds,
    )

    pipeline = EmailProcessingPipeline(
        mail_client,
        authoriser,
        ollama_client,
        command_parser,
        job_store,
        processed_store,
        outbox,
        admin_notifier,
        thread_matcher,
        settings.storage,
        settings.limits,
        settings.admin_email,
        diarisation_client=diarisation_client,
    )
    worker = JobWorker(
        job_store,
        diarisation_client,
        outbox,
        admin_notifier,
        settings.storage,
    )

    stop_event = threading.Event()
    api_server = None
    api_thread = None

    if settings.internal_api.enabled:
        if not settings.email_api_token:
            raise RuntimeError("internal_api.enabled is true but EMAIL_API_TOKEN is not set")
        api_server = EmailApiServer(
            (settings.internal_api.host, settings.internal_api.port),
            outbox,
            settings.email_api_token,
            settings.internal_api.max_body_chars,
        )
        api_thread = threading.Thread(
            target=api_server.serve_forever,
            name="internal-email-api",
            daemon=True,
        )

    def _handle_signal(signum, frame):
        logger.info("Received signal %s, shutting down...", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    def _mail_loop():
        while not stop_event.is_set():
            processed = 0
            sent = 0
            try:
                processed = pipeline.poll_once()
            except Exception:
                logger.exception("Error polling inbound mail")
            try:
                sent = pipeline.flush_outbox()
            except Exception:
                logger.exception("Error flushing outbound mail")
            if processed or sent:
                logger.info("Poll cycle: processed=%s sent=%s", processed, sent)
            stop_event.wait(settings.mail.poll_interval_seconds)

    worker_thread = threading.Thread(
        target=worker.run_forever,
        args=(settings.mail.poll_interval_seconds, stop_event),
        name="job-worker",
        daemon=True,
    )
    mail_thread = threading.Thread(target=_mail_loop, name="mail-pipeline", daemon=True)
    report_thread = None
    if settings.meeting_report.enabled:
        report_thread = threading.Thread(
            target=run_scheduler,
            args=(settings, stop_event),
            name="meeting-report",
            daemon=True,
        )

    logger.info("GroupAssessmentAgent starting (mail.provider=%s, llm.model=%s)", settings.mail.provider, settings.llm.model)
    worker_thread.start()
    mail_thread.start()
    if report_thread is not None:
        report_thread.start()
    if api_thread is not None:
        logger.info(
            "Internal email API listening on %s:%s",
            settings.internal_api.host,
            settings.internal_api.port,
        )
        api_thread.start()

    try:
        while not stop_event.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        stop_event.set()
    finally:
        if api_server is not None:
            api_server.shutdown()
            api_server.server_close()
        if api_thread is not None:
            api_thread.join(timeout=5.0)
        worker_thread.join(timeout=5.0)
        mail_thread.join(timeout=5.0)
        if report_thread is not None:
            report_thread.join(timeout=5.0)
        ollama_client.close()
        diarisation_client.close()
        logger.info("GroupAssessmentAgent stopped.")


def main() -> None:
    settings = load_settings()
    run(settings)


if __name__ == "__main__":
    main()
