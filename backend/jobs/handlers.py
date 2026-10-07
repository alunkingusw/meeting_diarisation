"""Job handlers: each runs on a worker thread with its own database session."""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any

from backend.db import SessionLocal
from backend.jobs.service import JobContext, handler
from backend.models import Group, Meeting, User, WeeklyReport, users_groups

logger = logging.getLogger(__name__)


@handler("transcript_processing")
def transcript_processing(ctx: JobContext, params: dict[str, Any]) -> dict[str, Any]:
    """Index an uploaded transcript for search, then generate its summary."""
    from backend.summarization.summariser import summarise_meeting_task
    from backend.transcript_rag.indexer import index_transcript

    ctx.progress("indexing transcript")
    index_transcript(
        group_id=params["group_id"],
        group_name=params["group_name"],
        meeting_id=params["meeting_id"],
        vtt_path=Path(params["transcript_path"]),
        meeting_title=params["group_name"],
        meeting_date=params["meeting_date"],
    )
    ctx.check_cancelled()
    ctx.progress("summarising meeting")
    with SessionLocal() as db:
        # Summarisation is best-effort: the transcript is already searchable if it fails.
        summarise_meeting_task(params["group_id"], params["meeting_id"], db)
        db.expire_all()
        meeting = db.get(Meeting, params["meeting_id"])
        summarised = bool(meeting and meeting.summary)
    return {"meeting_id": params["meeting_id"], "summarised": summarised}


@handler("transcription")
def transcription(ctx: JobContext, params: dict[str, Any]) -> dict[str, Any]:
    from backend.processing.transcribe import transcribe_meeting

    ctx.progress("transcribing audio")
    with SessionLocal() as db:
        transcribe_meeting(params["group_id"], params["meeting_id"], db)
    return {"meeting_id": params["meeting_id"]}


@handler("ingest")
def ingest(ctx: JobContext, params: dict[str, Any]) -> dict[str, Any]:
    from backend.project_rag.models import Repo
    from backend.project_rag.services.ingest_service import ingest_repo

    ctx.progress("ingesting GitHub/Trello activity")
    with SessionLocal() as db:
        repo = db.get(Repo, params["repo_id"])
        try:
            summary = ingest_repo(
                db, repo, local_path=Path(params["local_path"]), sources=tuple(params["sources"])
            )
        except Exception as exc:  # noqa: BLE001 - mirrored on the repo so ingest/status stays accurate
            db.rollback()
            repo.ingest_status, repo.ingest_error = "failed", str(exc)
            db.commit()
            raise
        repo.ingest_status, repo.ingest_error = "idle", None
        db.commit()
    return summary.model_dump(mode="json")


@handler("query")
def query(ctx: JobContext, params: dict[str, Any]) -> dict[str, Any]:
    """A group query that is too slow to hold an HTTP request open for."""
    from backend.engine.query_graph import run_unified_query
    from backend.project_rag import group_service
    from backend.project_rag.schemas import ConversationQueryRequest, QueryRequest, UnifiedQueryRequest

    scope, payload = params["scope"], params["payload"]
    ctx.progress(f"running {scope} query")
    with SessionLocal() as db:
        group = db.get(Group, params["group_id"])
        if scope == "unified":
            result = run_unified_query(db, group, UnifiedQueryRequest(**payload))
        else:
            request_cls = ConversationQueryRequest if scope == "conversation" else QueryRequest
            result = group_service.query_source(db, group, scope, request_cls(**payload))
    return result.model_dump(mode="json")


@handler("report")
def report(ctx: JobContext, params: dict[str, Any]) -> dict[str, Any]:
    from backend.engine.report_graph import compose_weekly_report

    ctx.progress("composing weekly report")
    with SessionLocal() as db:
        group = db.get(Group, params["group_id"])
        result = compose_weekly_report(
            db, group, date.fromisoformat(params["period_start"]), date.fromisoformat(params["period_end"])
        )
    return result.model_dump(mode="json")


@handler("weekly_reports")
def weekly_reports(ctx: JobContext, params: dict[str, Any]) -> dict[str, Any]:
    from backend.email_client import send_email
    from backend.engine.report_graph import compose_weekly_report

    period_start = date.fromisoformat(params["period_start"])
    period_end = date.fromisoformat(params["period_end"])
    with SessionLocal() as db:
        owner_rows = (
            db.query(Group.id, Group.name, User.email)
            .join(users_groups, users_groups.c.group_id == Group.id)
            .join(User, User.id == users_groups.c.user_id)
            .filter(users_groups.c.role == "owner", User.email.isnot(None))
            .order_by(Group.id, User.id)
            .all()
        )

    owners_by_group: dict[int, tuple[str, list[str]]] = {}
    for group_id, group_name, email in owner_rows:
        address = email.strip().lower()
        if not address:
            continue
        entry = owners_by_group.setdefault(group_id, (group_name or "", []))
        if address not in entry[1]:
            entry[1].append(address)

    queued_count = 0
    failed: list[dict[str, Any]] = []
    for group_id, (group_name, recipients) in owners_by_group.items():
        ctx.check_cancelled()
        report_id = f"WEEKLY-{period_start.isoformat()}-{group_id:04d}"
        try:
            with SessionLocal() as db:
                group = db.get(Group, group_id)
                report = db.get(WeeklyReport, report_id)
                if report is not None and report.status == "queued":
                    continue
                if report is None:
                    report = WeeklyReport(
                        report_id=report_id,
                        group_id=group_id,
                        group_name=group_name,
                        period_start=period_start,
                        period_end=period_end,
                        recipients=recipients,
                        queued_recipients=[],
                        status="generating",
                    )
                    db.add(report)
                    db.commit()
                else:
                    report.recipients = list(dict.fromkeys([*(report.recipients or []), *recipients]))
                    report.status, report.error = "generating", None
                    db.commit()

                if report.report_text is None:
                    result = compose_weekly_report(db, group, period_start, period_end)
                    report.report_text = result.report_text
                    report.model = result.model
                    report.evidence = [item.model_dump(mode="json") for item in result.evidence]
                    report.unavailable = result.unavailable
                    db.commit()

                subject = f"Weekly project update - {report.report_id}"
                body = (
                    f"Project: {report.group_name}\n"
                    f"Period: {report.period_start} to {report.period_end}\n\n"
                    f"{report.report_text}\n\n"
                    "Reply to this email with a question about this update."
                )
                queued = set(report.queued_recipients or [])
                for recipient in report.recipients:
                    if recipient in queued:
                        continue
                    send_email(recipient, subject, body, job_id=report.report_id)
                    queued.add(recipient)
                    report.queued_recipients = sorted(queued)
                    db.commit()

                report.status, report.error = "queued", None
                db.commit()
                queued_count += 1
        except Exception as exc:  # noqa: BLE001 - isolate failures to this group's report
            logger.exception("Weekly report %s failed", report_id)
            with SessionLocal() as db:
                report = db.get(WeeklyReport, report_id)
                if report is not None:
                    report.status, report.error = "failed", str(exc) or exc.__class__.__name__
                    db.commit()
            failed.append({"group_id": group_id, "error": str(exc)})

    return {"queued_groups": queued_count, "failed_groups": failed}
