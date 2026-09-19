"""Client for the internal email delivery service."""

import httpx

from backend.config import settings


class EmailError(RuntimeError):
    """Raised when the internal email service cannot send a message."""


def send_email(to: str, subject: str, body: str) -> None:
    """Send an email through the internal email delivery service."""
    if not settings.email_api_token:
        raise EmailError("EMAIL_API_TOKEN is not configured")

    try:
        response = httpx.post(
            settings.email_api_url,
            headers={"Authorization": f"Bearer {settings.email_api_token}"},
            json={"to": to, "subject": subject, "body": body},
            timeout=settings.email_timeout_seconds,
        )
        response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise EmailError(
            f"Email service timed out after {settings.email_timeout_seconds:.0f}s"
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise EmailError(
            f"Email service returned HTTP {exc.response.status_code}: "
            f"{exc.response.text.strip()}"
        ) from exc
    except httpx.HTTPError as exc:
        raise EmailError(f"Could not reach email service at {settings.email_api_url}") from exc