"""In-memory MailClient used by every automated test and available for local dev without a
live mailbox. Lets tests set arbitrary AuthSignals per message to exercise the authorisation
boundary, and records every sent message for assertions."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from app.mail.base import Attachment, EmailMessage, MailClient


@dataclass
class SentMessage:
    id: str
    to: str
    subject: str
    body_text: str
    attachments: list[tuple[str, bytes]] = field(default_factory=list)
    in_reply_to: Optional[str] = None
    references: Optional[str] = None


class FakeMailClient(MailClient):
    def __init__(self, messages: Optional[list[EmailMessage]] = None):
        self._inbox: list[EmailMessage] = list(messages or [])
        self._processed_refs: set[str] = set()
        self.sent: list[SentMessage] = []
        self._sent_counter = 0

    def add_message(self, message: EmailMessage) -> None:
        self._inbox.append(message)

    def fetch_new_messages(self, limit: int = 25) -> list[EmailMessage]:
        unseen = [m for m in self._inbox if m.provider_ref not in self._processed_refs]
        return unseen[:limit]

    def mark_processed(self, provider_ref: str) -> None:
        self._processed_refs.add(provider_ref)

    def send_email(
        self,
        to: str,
        subject: str,
        body_text: str,
        attachments: Optional[list[tuple[str, bytes]]] = None,
        in_reply_to: Optional[str] = None,
        references: Optional[str] = None,
    ) -> str:
        self._sent_counter += 1
        sent_id = f"<fake-sent-{self._sent_counter}@fake.test>"
        self.sent.append(
            SentMessage(
                id=sent_id,
                to=to,
                subject=subject,
                body_text=body_text,
                attachments=attachments or [],
                in_reply_to=in_reply_to,
                references=references,
            )
        )
        return sent_id


def make_test_email(
    from_address: str,
    subject: str = "Test email",
    body_text: str = "",
    message_id: Optional[str] = None,
    attachments: Optional[list[Attachment]] = None,
    auth_signals=None,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
) -> EmailMessage:
    """Convenience factory for building EmailMessage fixtures in tests."""
    from app.auth.authorisation import AuthSignals

    mid = message_id or f"<test-{id(object())}@fake.test>"
    return EmailMessage(
        message_id=mid,
        provider_ref=mid,
        from_address=from_address,
        subject=subject,
        body_text=body_text,
        received_at=datetime.now(timezone.utc),
        attachments=attachments or [],
        auth_signals=auth_signals or AuthSignals(spf="pass", dkim="pass", dmarc="pass"),
        in_reply_to=in_reply_to,
        references=references,
    )
