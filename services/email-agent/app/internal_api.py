"""Small authenticated HTTP API for internal outbound email requests."""
from __future__ import annotations

import json
import logging
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.jobs.store import Outbox

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^\s@,;]+@[^\s@,;]+\.[^\s@,;]+$")
_REQUEST_FIELDS = {"to", "subject", "body"}
_MAX_SUBJECT_LENGTH = 998


class EmailRequestHandler(BaseHTTPRequestHandler):
    server: "EmailApiServer"

    def do_POST(self) -> None:
        if self.path != "/internal/email":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return

        expected_token = self.server.auth_token
        authorization = self.headers.get("Authorization", "")
        if authorization != f"Bearer {expected_token}":
            self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return

        content_type = self.headers.get_content_type()
        if content_type != "application/json":
            self._send_json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "expected application/json"})
            return

        content_length = self.headers.get("Content-Length")
        try:
            length = int(content_length) if content_length is not None else -1
        except ValueError:
            length = -1
        if length < 0 or length > self.server.max_request_bytes:
            self._send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "request is too large"})
            return

        try:
            payload = json.loads(self.rfile.read(length))
            request = _validate_request(payload, self.server.max_body_chars)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return

        outbox_id = self.server.outbox.enqueue(
            to_email=request["to"],
            subject=request["subject"],
            body_text=request["body"],
        )
        self._send_json(HTTPStatus.ACCEPTED, {"outbox_id": outbox_id, "status": "queued"})

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._send_json(HTTPStatus.OK, {"status": "ok"})
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_PUT(self) -> None:
        self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method not allowed"})

    def do_DELETE(self) -> None:
        self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method not allowed"})

    def log_message(self, format: str, *args) -> None:
        logger.info("internal API: " + format, *args)

    def _send_json(self, status: HTTPStatus, payload: dict) -> None:
        response = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)


class EmailApiServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], outbox: Outbox, auth_token: str, max_body_chars: int):
        super().__init__(server_address, EmailRequestHandler)
        self.outbox = outbox
        self.auth_token = auth_token
        self.max_body_chars = max_body_chars
        self.max_request_bytes = max_body_chars + _MAX_SUBJECT_LENGTH + 512


def _validate_request(payload: object, max_body_chars: int) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise ValueError("request body must be a JSON object")
    if set(payload) != _REQUEST_FIELDS:
        raise ValueError("request must contain exactly: to, subject, body")
    if not all(isinstance(payload[field], str) for field in _REQUEST_FIELDS):
        raise ValueError("to, subject, and body must be strings")

    recipient = payload["to"].strip()
    subject = payload["subject"].strip()
    body = payload["body"]
    if not _EMAIL_RE.fullmatch(recipient):
        raise ValueError("to must contain one valid email address")
    if not subject:
        raise ValueError("subject must not be empty")
    if len(subject) > _MAX_SUBJECT_LENGTH:
        raise ValueError("subject is too long")
    if not body.strip():
        raise ValueError("body must not be empty")
    if len(body) > max_body_chars:
        raise ValueError("body is too long")

    return {"to": recipient, "subject": subject, "body": body}