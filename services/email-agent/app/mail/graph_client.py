"""Microsoft Graph mail client for a mailbox accessed via app-only (client credentials) OAuth2.

Requires an Azure AD app registration with Application permissions Mail.ReadWrite and
Mail.Send, admin consent granted, and (recommended) scoped to only this mailbox via
Exchange Online's New-ApplicationAccessPolicy rather than left as tenant-wide access - see
README "Mailbox setup" for the exact steps.

Graph has no first-class SPF/DKIM/DMARC verdict field, so the Authentication-Results header
that Exchange Online Protection adds is requested via internetMessageHeaders and parsed here -
this is the one real Graph-specific wrinkle the rest of the application never has to know about.

Always uses create-draft -> (optionally patch headers) -> send rather than the one-shot
/sendMail action: sendMail returns no body (so we couldn't recover the sent message's
internetMessageId for future thread matching), and does not reliably support setting arbitrary
In-Reply-To/References headers.
"""
from __future__ import annotations

import base64
import re
from datetime import datetime, timezone
from typing import Optional

import httpx
import msal

from app.auth.authorisation import AuthSignals
from app.mail.base import Attachment, EmailMessage, MailClient

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPE = ["https://graph.microsoft.com/.default"]

_AUTH_RESULTS_HEADER_NAMES = {"authentication-results"}
_VERDICT_RE = re.compile(r"\b(spf|dkim|dmarc)\s*=\s*([a-zA-Z]+)")

_MESSAGE_SELECT_FIELDS = ",".join(
    [
        "id",
        "subject",
        "from",
        "receivedDateTime",
        "body",
        "internetMessageId",
        "internetMessageHeaders",
        "hasAttachments",
    ]
)


class GraphMailClient(MailClient):
    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        mailbox_upn: str,
        timeout: float = 30.0,
    ):
        self._mailbox_upn = mailbox_upn
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._client_secret = client_secret
        self._msal_app: Optional[msal.ConfidentialClientApplication] = None
        self._client = httpx.Client(base_url=GRAPH_BASE_URL, timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def _get_msal_app(self) -> msal.ConfidentialClientApplication:
        # Built lazily (on first token request) rather than in __init__: MSAL performs a real
        # tenant-discovery network call as soon as the ConfidentialClientApplication is
        # constructed, which would otherwise make every GraphMailClient instantiation - and
        # every test of the rest of this class - depend on network access.
        if self._msal_app is None:
            self._msal_app = msal.ConfidentialClientApplication(
                self._client_id,
                authority=f"https://login.microsoftonline.com/{self._tenant_id}",
                client_credential=self._client_secret,
            )
        return self._msal_app

    def _headers(self) -> dict:
        # MSAL's ConfidentialClientApplication caches tokens internally and only makes a
        # network call when the cached one is missing/expired.
        result = self._get_msal_app().acquire_token_for_client(scopes=GRAPH_SCOPE)
        if "access_token" not in result:
            raise RuntimeError(
                "Could not acquire a Graph token: "
                f"{result.get('error')}: {result.get('error_description')}"
            )
        return {"Authorization": f"Bearer {result['access_token']}"}

    # --- MailClient interface --------------------------------------------------------------

    def fetch_new_messages(self, limit: int = 25) -> list[EmailMessage]:
        params = {
            "$filter": "isRead eq false",
            "$orderby": "receivedDateTime asc",
            "$top": str(limit),
            "$select": _MESSAGE_SELECT_FIELDS,
        }
        resp = self._client.get(
            f"/users/{self._mailbox_upn}/mailFolders/Inbox/messages",
            headers=self._headers(),
            params=params,
        )
        resp.raise_for_status()
        return [self._to_email_message(item) for item in resp.json().get("value", [])]

    def mark_processed(self, provider_ref: str) -> None:
        resp = self._client.patch(
            f"/users/{self._mailbox_upn}/messages/{provider_ref}",
            headers=self._headers(),
            json={"isRead": True},
        )
        resp.raise_for_status()

    def send_email(
        self,
        to: str,
        subject: str,
        body_text: str,
        attachments: Optional[list[tuple[str, bytes]]] = None,
        in_reply_to: Optional[str] = None,
        references: Optional[str] = None,
    ) -> str:
        draft_body: dict = {
            "subject": subject,
            "body": {"contentType": "Text", "content": body_text},
            "toRecipients": [{"emailAddress": {"address": to}}],
        }
        if attachments:
            draft_body["attachments"] = [
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": name,
                    "contentBytes": base64.b64encode(content).decode("ascii"),
                }
                for name, content in attachments
            ]

        resp = self._client.post(
            f"/users/{self._mailbox_upn}/messages", headers=self._headers(), json=draft_body
        )
        resp.raise_for_status()
        draft = resp.json()
        draft_id = draft["id"]
        internet_message_id = draft.get("internetMessageId", draft_id)

        if in_reply_to or references:
            header_updates = []
            if in_reply_to:
                header_updates.append({"name": "In-Reply-To", "value": in_reply_to})
            if references:
                header_updates.append({"name": "References", "value": references})
            patch_resp = self._client.patch(
                f"/users/{self._mailbox_upn}/messages/{draft_id}",
                headers=self._headers(),
                json={"internetMessageHeaders": header_updates},
            )
            patch_resp.raise_for_status()

        send_resp = self._client.post(
            f"/users/{self._mailbox_upn}/messages/{draft_id}/send", headers=self._headers()
        )
        send_resp.raise_for_status()
        return internet_message_id

    # --- Graph-specific plumbing -------------------------------------------------------------

    def _to_email_message(self, item: dict) -> EmailMessage:
        graph_id = item["id"]
        attachments = self._fetch_attachments(graph_id) if item.get("hasAttachments") else []
        headers = item.get("internetMessageHeaders") or []

        return EmailMessage(
            message_id=item.get("internetMessageId") or graph_id,
            provider_ref=graph_id,
            from_address=((item.get("from") or {}).get("emailAddress") or {}).get("address", ""),
            subject=item.get("subject") or "",
            body_text=_extract_body_text(item.get("body") or {}),
            received_at=_parse_datetime(item.get("receivedDateTime")),
            attachments=attachments,
            auth_signals=_parse_auth_signals(headers),
            in_reply_to=_header_value(headers, "in-reply-to"),
            references=_header_value(headers, "references"),
        )

    def _fetch_attachments(self, graph_message_id: str) -> list[Attachment]:
        resp = self._client.get(
            f"/users/{self._mailbox_upn}/messages/{graph_message_id}/attachments",
            headers=self._headers(),
        )
        resp.raise_for_status()
        result = []
        for item in resp.json().get("value", []):
            if item.get("@odata.type") != "#microsoft.graph.fileAttachment":
                continue  # skip item/reference attachments - only real files are usable here
            content = base64.b64decode(item["contentBytes"]) if item.get("contentBytes") else b""
            result.append(
                Attachment(
                    filename=item.get("name", "attachment"),
                    content_type=item.get("contentType", "application/octet-stream"),
                    content=content,
                )
            )
        return result


def _extract_body_text(body: dict) -> str:
    content = body.get("content", "")
    if (body.get("contentType") or "").lower() == "html":
        return _strip_html(content)
    return content


def _strip_html(html: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def _parse_datetime(value: Optional[str]) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _parse_auth_signals(headers: list[dict]) -> AuthSignals:
    raw = _header_value(headers, "authentication-results")
    if raw is None:
        return AuthSignals()
    verdicts = {m.group(1).lower(): m.group(2).lower() for m in _VERDICT_RE.finditer(raw)}
    return AuthSignals(
        spf=verdicts.get("spf"), dkim=verdicts.get("dkim"), dmarc=verdicts.get("dmarc"), raw_header=raw
    )


def _header_value(headers: list[dict], name: str) -> Optional[str]:
    for header in headers:
        if (header.get("name") or "").lower() == name:
            return header.get("value")
    return None
