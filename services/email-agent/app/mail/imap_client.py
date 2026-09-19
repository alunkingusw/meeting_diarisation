"""Generic IMAP/SMTP mail client for project mailboxes such as mailbox.org."""
from __future__ import annotations

import imaplib
import re
import smtplib
from datetime import datetime, timezone
from email import encoders
from email import policy
from email.header import decode_header, make_header
from email.message import Message
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.parser import BytesParser
from email.utils import make_msgid
from typing import Optional

from app.auth.authorisation import AuthSignals
from app.mail.base import Attachment, EmailMessage, MailClient

_DEFAULT_IMAP_HOST = "imap.mailbox.org"
_DEFAULT_SMTP_HOST = "smtp.mailbox.org"
_VERDICT_RE = re.compile(r"\b(spf|dkim|dmarc)\s*=\s*([a-zA-Z]+)")


class ImapMailClient(MailClient):
    def __init__(
        self,
        username: str,
        password: str,
        mailbox_name: str = "INBOX",
        imap_host: str = _DEFAULT_IMAP_HOST,
        smtp_host: str = _DEFAULT_SMTP_HOST,
        timeout: float = 30.0,
    ):
        self._username = username
        self._password = password
        self._mailbox_name = mailbox_name or "INBOX"
        self._imap_host = imap_host
        self._smtp_host = smtp_host
        self._timeout = timeout

    def _imap_connection(self) -> imaplib.IMAP4_SSL:
        client = imaplib.IMAP4_SSL(self._imap_host, timeout=self._timeout)
        client.login(self._username, self._password)
        return client

    def _smtp_connection(self) -> smtplib.SMTP_SSL:
        client = smtplib.SMTP_SSL(self._smtp_host, 465, timeout=self._timeout)
        client.login(self._username, self._password)
        return client

    def fetch_new_messages(self, limit: int = 25) -> list[EmailMessage]:
        with self._imap_connection() as client:
            client.select(self._mailbox_name, readonly=True)
            status, data = client.search(None, "UNSEEN")
            if status != "OK":
                return []

            ids = data[0].split() if data and data[0] else []
            results: list[EmailMessage] = []
            for message_id in reversed(ids[-limit:]):
                status, fetch_data = client.fetch(message_id, "(RFC822)")
                if status != "OK" or not fetch_data or not fetch_data[0]:
                    continue
                raw_message = fetch_data[0][1]
                msg = BytesParser(policy=policy.default).parsebytes(raw_message)
                results.append(self._to_email_message(msg, provider_ref=message_id.decode("ascii")))
            return results

    def mark_processed(self, provider_ref: str) -> None:
        with self._imap_connection() as client:
            client.select(self._mailbox_name)
            client.store(provider_ref, "+FLAGS", "\\Seen")

    def send_email(
        self,
        to: str,
        subject: str,
        body_text: str,
        attachments: Optional[list[tuple[str, bytes]]] = None,
        in_reply_to: Optional[str] = None,
        references: Optional[str] = None,
    ) -> str:
        message = MIMEMultipart()
        message["From"] = self._username
        message["To"] = to
        message["Subject"] = subject
        if in_reply_to:
            message["In-Reply-To"] = in_reply_to
        if references:
            message["References"] = references
        message["Message-ID"] = make_msgid(domain=self._smtp_host.split(".", 1)[1])
        message.attach(MIMEText(body_text, "plain", "utf-8"))

        for filename, content in attachments or []:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(content)
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", "attachment", filename=filename)
            message.attach(part)

        with self._smtp_connection() as smtp_client:
            smtp_client.send_message(message)

        return message["Message-ID"]

    def _to_email_message(self, msg: Message, provider_ref: str) -> EmailMessage:
        return EmailMessage(
            message_id=msg.get("Message-ID") or provider_ref,
            provider_ref=provider_ref,
            from_address=_extract_address(msg.get("From")) or "",
            subject=_decode_header(msg.get("Subject")) or "",
            body_text=_extract_body_text(msg),
            received_at=_parse_datetime(msg.get("Date")),
            attachments=_extract_attachments(msg),
            auth_signals=_parse_auth_signals(msg),
            in_reply_to=msg.get("In-Reply-To"),
            references=msg.get("References"),
        )


def _extract_body_text(msg: Message) -> str:
    if msg.is_multipart():
        text_parts: list[str] = []
        for part in msg.walk():
            if part.is_multipart():
                continue
            if part.get_content_disposition() == "attachment":
                continue
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                text_parts.append(payload.decode(part.get_content_charset() or "utf-8", errors="replace"))
                continue
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                text_parts.append(_strip_html(payload.decode(part.get_content_charset() or "utf-8", errors="replace")))
        return "\n\n".join(text_parts).strip()

    payload = msg.get_payload(decode=True)
    if payload is None:
        return ""
    if msg.get_content_type() == "text/html":
        return _strip_html(payload.decode(msg.get_content_charset() or "utf-8", errors="replace"))
    return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")


def _strip_html(html: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def _extract_attachments(msg: Message) -> list[Attachment]:
    attachments: list[Attachment] = []
    if not msg.is_multipart():
        return attachments
    for part in msg.walk():
        if part.get_content_disposition() != "attachment":
            continue
        filename = part.get_filename() or "attachment"
        payload = part.get_payload(decode=True)
        if payload is None:
            payload = b""
        attachments.append(
            Attachment(
                filename=filename,
                content_type=part.get_content_type() or "application/octet-stream",
                content=payload,
            )
        )
    return attachments


def _decode_header(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _extract_address(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    match = re.search(r"<([^>]+)>", value)
    if match:
        return match.group(1).strip().lower()
    return value.strip().lower()


def _parse_datetime(value: Optional[str]) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        return datetime.strptime(value, "%a, %d %b %Y %H:%M:%S %z")
    except ValueError:
        try:
            return datetime.strptime(value, "%a, %d %b %Y %H:%M:%S")
        except ValueError:
            return datetime.now(timezone.utc)


def _parse_auth_signals(msg: Message) -> AuthSignals:
    raw = msg.get("Authentication-Results") or msg.get("Received-SPF") or ""
    if not raw:
        return AuthSignals()
    verdicts = {m.group(1).lower(): m.group(2).lower() for m in _VERDICT_RE.finditer(raw)}
    return AuthSignals(
        spf=verdicts.get("spf"),
        dkim=verdicts.get("dkim"),
        dmarc=verdicts.get("dmarc"),
        raw_header=raw,
    )
