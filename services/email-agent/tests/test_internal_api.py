import json
import threading
from http.client import HTTPConnection
from pathlib import Path

from app.internal_api import EmailApiServer
from app.jobs.store import Outbox


def _request(server: EmailApiServer, method: str, path: str, body=None, token: str = "secret"):
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        connection = HTTPConnection(*server.server_address)
        headers = {"Authorization": f"Bearer {token}"}
        encoded_body = None
        if body is not None:
            encoded_body = json.dumps(body)
            headers["Content-Type"] = "application/json"
            headers["Content-Length"] = str(len(encoded_body.encode("utf-8")))
        connection.request(method, path, body=encoded_body, headers=headers)
        response = connection.getresponse()
        result = json.loads(response.read())
        connection.close()
        return response.status, result
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)


def _server(db_path: Path) -> EmailApiServer:
    return EmailApiServer(("127.0.0.1", 0), Outbox(db_path), "secret", max_body_chars=100)


def test_send_request_is_queued(db_path: Path):
    status, result = _request(
        _server(db_path),
        "POST",
        "/internal/email",
        {"to": "alice@example.com", "subject": "Hello", "body": "Message"},
    )

    assert status == 202
    assert result["status"] == "queued"
    pending = Outbox(db_path).pending()
    assert pending[0].to_email == "alice@example.com"
    assert pending[0].body_text == "Message"


def test_send_request_requires_token(db_path: Path):
    status, result = _request(
        _server(db_path),
        "POST",
        "/internal/email",
        {"to": "alice@example.com", "subject": "Hello", "body": "Message"},
        token="wrong",
    )

    assert status == 401
    assert result == {"error": "unauthorized"}
    assert Outbox(db_path).pending() == []


def test_send_request_rejects_extra_fields_and_invalid_recipient(db_path: Path):
    status, result = _request(
        _server(db_path),
        "POST",
        "/internal/email",
        {"to": "not-an-email", "subject": "Hello", "body": "Message", "job_id": "x"},
    )

    assert status == 400
    assert "exactly" in result["error"]
    assert Outbox(db_path).pending() == []