import imaplib
from email import policy
from email.parser import BytesParser
from unittest.mock import MagicMock

import pytest

from app.mail.imap_client import ImapMailClient


def test_fetch_new_messages_reports_mailbox_selection_failure(monkeypatch):
    client = ImapMailClient(username="user@example.com", password="password")
    connection = MagicMock()
    imap = connection.__enter__.return_value
    imap.select.return_value = ("NO", [b"Mailbox unavailable"])
    monkeypatch.setattr(client, "_imap_connection", lambda: connection)

    with pytest.raises(imaplib.IMAP4.error, match="Could not select mailbox"):
        client.fetch_new_messages()

    imap.search.assert_not_called()


def test_send_email_appends_copy_to_sent_folder(monkeypatch):
    client = ImapMailClient(username="user@example.com", password="password")
    smtp_connection = MagicMock()
    imap_connection = MagicMock()
    smtp_client = smtp_connection.__enter__.return_value
    imap_client = imap_connection.__enter__.return_value
    imap_client.append.return_value = ("OK", [b"1"])
    monkeypatch.setattr(client, "_smtp_connection", lambda: smtp_connection)
    monkeypatch.setattr(client, "_imap_connection", lambda: imap_connection)

    message_id = client.send_email("alice@example.com", "Meeting notes", "Original outline")

    smtp_client.send_message.assert_called_once()
    imap_client.append.assert_called_once()
    args = imap_client.append.call_args.args
    assert args[:3] == ("Sent", "\\Seen", None)
    assert b"Subject: Meeting notes" in args[3]
    archived = BytesParser(policy=policy.default).parsebytes(args[3])
    assert archived.get_body(preferencelist=("plain",)).get_content() == "Original outline"
    assert message_id.startswith("<")


def test_sent_folder_append_failure_does_not_fail_successful_send(monkeypatch, caplog):
    client = ImapMailClient(username="user@example.com", password="password")
    smtp_connection = MagicMock()
    imap_connection = MagicMock()
    smtp_client = smtp_connection.__enter__.return_value
    imap_client = imap_connection.__enter__.return_value
    imap_client.append.side_effect = OSError("Sent folder unavailable")
    monkeypatch.setattr(client, "_smtp_connection", lambda: smtp_connection)
    monkeypatch.setattr(client, "_imap_connection", lambda: imap_connection)

    message_id = client.send_email("alice@example.com", "Meeting notes", "Original outline")

    smtp_client.send_message.assert_called_once()
    assert message_id.startswith("<")
    assert "Could not save sent email" in caplog.text