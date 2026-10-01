import pytest

from app.main import build_mail_client
from app.mail.imap_client import ImapMailClient
from app.settings import Settings


def test_build_mail_client_supports_mail_provider():
    settings = Settings(
        mail={"provider": "mail", "mailbox_upn": "project@provider.example"},
        mail_username="project@provider.example",
        mail_password="secret",
    )

    client = build_mail_client(settings)

    assert isinstance(client, ImapMailClient)
    assert client._username == "project@provider.example"
    assert client._mailbox_name == "INBOX"


def test_build_mail_client_requires_mail_credentials():
    settings = Settings(mail={"provider": "mail"})

    with pytest.raises(RuntimeError, match="MAIL_USERNAME|MAIL_PASSWORD"):
        build_mail_client(settings)
