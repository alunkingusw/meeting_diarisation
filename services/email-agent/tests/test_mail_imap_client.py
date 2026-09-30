import imaplib
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