from datetime import date, datetime, time, timedelta
from pathlib import Path
from string import Template
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth import get_current_user_id
from backend.db_dependency import get_db
from backend.email_client import EmailError, send_email
from backend.models import Group, Meeting, MeetingComment, User, users_groups

router = APIRouter(prefix="/reports", tags=["reports"])

REPORT_TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "templates" / "group_report_email.txt"


class ReportRequest(BaseModel):
    start_date: date
    end_date: date  # inclusive


class GroupReportResult(BaseModel):
    group_id: int
    group_name: str
    meeting_count: int
    emailed: bool
    detail: str


def _format_meeting(meeting: Meeting) -> str:
    lines = [f"Meeting {meeting.id} - {meeting.date.date().isoformat()}"]
    lines.append(meeting.summary.strip() if meeting.summary else "(No summary has been generated for this meeting.)")
    if meeting.comments:
        lines.append("Comments:")
        for comment in sorted(meeting.comments, key=lambda c: c.created):
            lines.append(
                f"- {_comment_author(comment)} ({comment.created.date().isoformat()}): "
                f"{comment.comment.strip()}"
            )
    else:
        lines.append("Comments: none")
    return "\n".join(lines)


def _comment_author(comment: MeetingComment) -> str:
    if comment.group_member and comment.group_member.name:
        return comment.group_member.name
    if comment.user and comment.user.username:
        return comment.user.username
    return "Unknown"


def _render_report(group: Group, meetings: List[Meeting], start: date, end: date) -> tuple[str, str]:
    template_lines = REPORT_TEMPLATE_PATH.read_text(encoding="utf-8").splitlines()
    template_text = "\n".join(line for line in template_lines if not line.startswith("#"))
    name = group.name or "Unnamed group"
    body = Template(template_text).substitute(
        group_name=name,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        meeting_count=len(meetings),
        meetings="\n\n".join(_format_meeting(m) for m in meetings),
    )
    subject = f"Report: {name} {start.isoformat()} to {end.isoformat()} [group_id={group.id}]"
    return subject, body.strip()


@router.post("/generate_report", response_model=List[GroupReportResult])
def generate_report(
    request: ReportRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Email the current user one report per group they supervise, built from stored
    meeting summaries for meetings dated between start_date and end_date inclusive."""
    if request.end_date < request.start_date:
        raise HTTPException(status_code=422, detail="end_date must not be before start_date")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.email or not user.email.strip():
        raise HTTPException(status_code=400, detail="User has no email address")

    range_start = datetime.combine(request.start_date, time.min)
    range_end = datetime.combine(request.end_date + timedelta(days=1), time.min)

    groups = (
        db.query(Group)
        .join(users_groups, users_groups.c.group_id == Group.id)
        .filter(users_groups.c.user_id == user_id, users_groups.c.role == "owner")
        .order_by(Group.id)
        .all()
    )

    results: List[GroupReportResult] = []
    for group in groups:
        name = group.name or "Unnamed group"
        meetings = (
            db.query(Meeting)
            .filter(Meeting.group_id == group.id, Meeting.date >= range_start, Meeting.date < range_end)
            .order_by(Meeting.date)
            .all()
        )
        if not meetings:
            results.append(GroupReportResult(
                group_id=group.id, group_name=name, meeting_count=0,
                emailed=False, detail="No meetings in range; no email sent",
            ))
            continue

        subject, body = _render_report(group, meetings, request.start_date, request.end_date)
        try:
            send_email(to=user.email.strip(), subject=subject, body=body)
        except EmailError as exc:
            results.append(GroupReportResult(
                group_id=group.id, group_name=name, meeting_count=len(meetings),
                emailed=False, detail=f"Email failed: {exc}",
            ))
            continue
        results.append(GroupReportResult(
            group_id=group.id, group_name=name, meeting_count=len(meetings),
            emailed=True, detail="Report emailed",
        ))
    return results
