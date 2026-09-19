import base64

import httpx
import pytest
import respx

from app.mail.graph_client import GRAPH_BASE_URL, GraphMailClient

MAILBOX = "diarisation@uni.onmicrosoft.com"


@pytest.fixture
def client(monkeypatch):
    c = GraphMailClient("tenant", "client-id", "secret", MAILBOX, timeout=1.0)
    monkeypatch.setattr(c, "_headers", lambda: {"Authorization": "Bearer faketoken"})
    yield c
    c.close()


def _list_messages_response(items):
    return httpx.Response(200, json={"value": items})


@respx.mock
def test_fetch_new_messages_maps_basic_fields(client):
    respx.get(f"{GRAPH_BASE_URL}/users/{MAILBOX}/mailFolders/Inbox/messages").mock(
        return_value=_list_messages_response(
            [
                {
                    "id": "graph-id-1",
                    "internetMessageId": "<abc@mail>",
                    "subject": "Hello",
                    "from": {"emailAddress": {"address": "alice@uni.ac.uk"}},
                    "receivedDateTime": "2026-08-11T10:00:00Z",
                    "body": {"contentType": "text", "content": "Plain body text."},
                    "hasAttachments": False,
                    "internetMessageHeaders": [],
                }
            ]
        )
    )
    messages = client.fetch_new_messages()
    assert len(messages) == 1
    msg = messages[0]
    assert msg.message_id == "<abc@mail>"
    assert msg.provider_ref == "graph-id-1"
    assert msg.from_address == "alice@uni.ac.uk"
    assert msg.subject == "Hello"
    assert msg.body_text == "Plain body text."
    assert msg.received_at.year == 2026
    assert msg.attachments == []


@respx.mock
def test_fetch_new_messages_strips_html_body(client):
    respx.get(f"{GRAPH_BASE_URL}/users/{MAILBOX}/mailFolders/Inbox/messages").mock(
        return_value=_list_messages_response(
            [
                {
                    "id": "graph-id-1",
                    "internetMessageId": "<abc@mail>",
                    "subject": "Hello",
                    "from": {"emailAddress": {"address": "alice@uni.ac.uk"}},
                    "receivedDateTime": "2026-08-11T10:00:00Z",
                    "body": {
                        "contentType": "html",
                        "content": "<p>Hello <b>there</b></p><p>Second paragraph</p>",
                    },
                    "hasAttachments": False,
                    "internetMessageHeaders": [],
                }
            ]
        )
    )
    msg = client.fetch_new_messages()[0]
    assert "<" not in msg.body_text
    assert "Hello there" in msg.body_text
    assert "Second paragraph" in msg.body_text


@respx.mock
def test_fetch_new_messages_downloads_and_decodes_attachments(client):
    respx.get(f"{GRAPH_BASE_URL}/users/{MAILBOX}/mailFolders/Inbox/messages").mock(
        return_value=_list_messages_response(
            [
                {
                    "id": "graph-id-1",
                    "internetMessageId": "<abc@mail>",
                    "subject": "Transcript",
                    "from": {"emailAddress": {"address": "alice@uni.ac.uk"}},
                    "receivedDateTime": "2026-08-11T10:00:00Z",
                    "body": {"contentType": "text", "content": "See attached."},
                    "hasAttachments": True,
                    "internetMessageHeaders": [],
                }
            ]
        )
    )
    encoded = base64.b64encode(b"WEBVTT\n\n1\n00:00:01.000 --> 00:00:02.000\nAlice: hi\n").decode()
    respx.get(f"{GRAPH_BASE_URL}/users/{MAILBOX}/messages/graph-id-1/attachments").mock(
        return_value=httpx.Response(
            200,
            json={
                "value": [
                    {
                        "@odata.type": "#microsoft.graph.fileAttachment",
                        "name": "meeting.vtt",
                        "contentType": "text/vtt",
                        "contentBytes": encoded,
                    },
                    {
                        # A reference/item attachment (e.g. a OneDrive link) - must be skipped,
                        # never treated as a usable file attachment.
                        "@odata.type": "#microsoft.graph.referenceAttachment",
                        "name": "shared-link",
                    },
                ]
            },
        )
    )

    msg = client.fetch_new_messages()[0]
    assert len(msg.attachments) == 1
    assert msg.attachments[0].filename == "meeting.vtt"
    assert msg.attachments[0].content.startswith(b"WEBVTT")


@respx.mock
def test_authentication_results_header_is_parsed_into_auth_signals(client):
    respx.get(f"{GRAPH_BASE_URL}/users/{MAILBOX}/mailFolders/Inbox/messages").mock(
        return_value=_list_messages_response(
            [
                {
                    "id": "graph-id-1",
                    "internetMessageId": "<abc@mail>",
                    "subject": "Hi",
                    "from": {"emailAddress": {"address": "alice@uni.ac.uk"}},
                    "receivedDateTime": "2026-08-11T10:00:00Z",
                    "body": {"contentType": "text", "content": "Hi"},
                    "hasAttachments": False,
                    "internetMessageHeaders": [
                        {
                            "name": "Authentication-Results",
                            "value": (
                                "spf=pass smtp.mailfrom=uni.ac.uk; dkim=pass "
                                "header.d=uni.ac.uk; dmarc=pass action=none "
                                "header.from=uni.ac.uk"
                            ),
                        }
                    ],
                }
            ]
        )
    )
    msg = client.fetch_new_messages()[0]
    assert msg.auth_signals.spf == "pass"
    assert msg.auth_signals.dkim == "pass"
    assert msg.auth_signals.dmarc == "pass"
    assert "dmarc=pass" in msg.auth_signals.raw_header


@respx.mock
def test_missing_authentication_results_header_yields_empty_auth_signals(client):
    respx.get(f"{GRAPH_BASE_URL}/users/{MAILBOX}/mailFolders/Inbox/messages").mock(
        return_value=_list_messages_response(
            [
                {
                    "id": "graph-id-1",
                    "internetMessageId": "<abc@mail>",
                    "subject": "Hi",
                    "from": {"emailAddress": {"address": "alice@uni.ac.uk"}},
                    "receivedDateTime": "2026-08-11T10:00:00Z",
                    "body": {"contentType": "text", "content": "Hi"},
                    "hasAttachments": False,
                    "internetMessageHeaders": [],
                }
            ]
        )
    )
    msg = client.fetch_new_messages()[0]
    assert msg.auth_signals.spf is None
    assert msg.auth_signals.dkim is None
    assert msg.auth_signals.dmarc is None


@respx.mock
def test_mark_processed_sets_is_read(client):
    route = respx.patch(f"{GRAPH_BASE_URL}/users/{MAILBOX}/messages/graph-id-1").mock(
        return_value=httpx.Response(200, json={})
    )
    client.mark_processed("graph-id-1")
    assert route.called
    import json

    assert json.loads(route.calls.last.request.content) == {"isRead": True}


@respx.mock
def test_send_email_without_threading_creates_draft_and_sends(client):
    create_route = respx.post(f"{GRAPH_BASE_URL}/users/{MAILBOX}/messages").mock(
        return_value=httpx.Response(
            201, json={"id": "draft-1", "internetMessageId": "<sent-1@mail>"}
        )
    )
    patch_route = respx.patch(f"{GRAPH_BASE_URL}/users/{MAILBOX}/messages/draft-1").mock(
        return_value=httpx.Response(200, json={})
    )
    send_route = respx.post(f"{GRAPH_BASE_URL}/users/{MAILBOX}/messages/draft-1/send").mock(
        return_value=httpx.Response(202)
    )

    result = client.send_email(to="alice@uni.ac.uk", subject="Hi", body_text="Body")

    assert result == "<sent-1@mail>"
    assert create_route.called
    assert send_route.called
    assert not patch_route.called  # no threading requested - no header patch needed


@respx.mock
def test_send_email_with_reply_headers_patches_before_sending(client):
    respx.post(f"{GRAPH_BASE_URL}/users/{MAILBOX}/messages").mock(
        return_value=httpx.Response(201, json={"id": "draft-1", "internetMessageId": "<sent-1@mail>"})
    )
    patch_route = respx.patch(f"{GRAPH_BASE_URL}/users/{MAILBOX}/messages/draft-1").mock(
        return_value=httpx.Response(200, json={})
    )
    respx.post(f"{GRAPH_BASE_URL}/users/{MAILBOX}/messages/draft-1/send").mock(
        return_value=httpx.Response(202)
    )

    client.send_email(
        to="alice@uni.ac.uk", subject="Re: Hi", body_text="Body", in_reply_to="<orig@mail>"
    )

    assert patch_route.called
    import json

    body = json.loads(patch_route.calls.last.request.content)
    assert {"name": "In-Reply-To", "value": "<orig@mail>"} in body["internetMessageHeaders"]


@respx.mock
def test_send_email_with_attachments_base64_encodes_content(client):
    create_route = respx.post(f"{GRAPH_BASE_URL}/users/{MAILBOX}/messages").mock(
        return_value=httpx.Response(201, json={"id": "draft-1", "internetMessageId": "<sent-1@mail>"})
    )
    respx.post(f"{GRAPH_BASE_URL}/users/{MAILBOX}/messages/draft-1/send").mock(
        return_value=httpx.Response(202)
    )

    client.send_email(
        to="alice@uni.ac.uk",
        subject="Results",
        body_text="See attached",
        attachments=[("meeting.vtt", b"WEBVTT\n")],
    )

    import json

    body = json.loads(create_route.calls.last.request.content)
    assert body["attachments"][0]["name"] == "meeting.vtt"
    assert base64.b64decode(body["attachments"][0]["contentBytes"]) == b"WEBVTT\n"
