"""Mail provider abstraction.

GraphMailClient (mail/graph_client.py) is the concrete implementation used against a
Microsoft 365 mailbox. FakeMailClient (mail/fake_client.py) backs all automated tests and local
development without a live mailbox. Both implement this same interface so the rest of the
application never depends on a specific mail provider.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.auth.authorisation import AuthSignals


@dataclass
class Attachment:
    filename: str
    content_type: str
    content: bytes

    @property
    def size_bytes(self) -> int:
        return len(self.content)


@dataclass
class EmailMessage:
    message_id: str  # RFC822 Message-ID (falls back to a synthetic value if the provider lacks one)
    provider_ref: str  # provider-specific id used for mark_processed() and threaded replies
    from_address: str
    subject: str
    body_text: str
    received_at: datetime
    attachments: list[Attachment] = field(default_factory=list)
    auth_signals: AuthSignals = field(default_factory=AuthSignals)
    in_reply_to: Optional[str] = None
    references: Optional[str] = None


class MailClient(ABC):
    @abstractmethod
    def fetch_new_messages(self, limit: int = 25) -> list[EmailMessage]:
        """Returns unread/new messages, oldest first."""

    @abstractmethod
    def mark_processed(self, provider_ref: str) -> None:
        """Marks a message as handled (e.g. isRead=true). Never deletes the original - spec S5."""

    @abstractmethod
    def send_email(
        self,
        to: str,
        subject: str,
        body_text: str,
        attachments: Optional[list[tuple[str, bytes]]] = None,
        in_reply_to: Optional[str] = None,
        references: Optional[str] = None,
    ) -> str:
        """Sends an email. Returns the provider's Message-ID for the sent message, so it can
        be recorded for future thread matching."""
