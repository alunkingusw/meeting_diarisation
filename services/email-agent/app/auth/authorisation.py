"""Deterministic sender authorisation - runs *before* the LLM is ever invoked (spec S4).

Implements the three-tier reply model for this university deployment:

1. authorised          - auth signals pass AND the address is a registered group owner
                          -> proceed normally.
2. unrecognised_in_domain - auth signals pass, the address's domain is one of
                          AUTHORISED_EMAIL_DOMAINS, but it isn't a registered owner
                          -> a friendly "you're not registered" reply is sent (this is an
                          expected onboarding case for a university mailbox).
3. unauthorised_external / unauthenticated / malformed_sender
                          -> silent drop, no reply (replying would confirm a monitored mailbox
                          exists to arbitrary internet senders; a domain claim without a
                          passing SPF/DKIM/DMARC check can't be trusted anyway).

All five reasons are logged and (for anything but "authorised") admin-alertable by the caller.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthResultReason(str, Enum):
    AUTHORISED = "authorised"
    UNRECOGNISED_IN_DOMAIN = "unrecognised_in_domain"
    UNAUTHORISED_EXTERNAL = "unauthorised_external"
    UNAUTHENTICATED = "unauthenticated"
    MALFORMED_SENDER = "malformed_sender"


@dataclass
class AuthSignals:
    """The mail provider's verdict on SPF/DKIM/DMARC for this message, where available.
    Values are provider-reported strings (e.g. "pass", "fail", "softfail", "none") or None
    if the provider didn't surface a verdict at all."""

    spf: Optional[str] = None
    dkim: Optional[str] = None
    dmarc: Optional[str] = None
    raw_header: Optional[str] = None  # the raw Authentication-Results header, kept for audit logs


@dataclass
class SenderAuthResult:
    ok: bool
    user_id: Optional[int]
    sender_email: Optional[str]
    reason: AuthResultReason


class SenderAuthoriser:
    def __init__(
        self,
        group_owners: dict[str, int],
        authorised_domains: list[str],
        require_auth_pass: bool = True,
    ):
        self._group_owners = {k.strip().lower(): v for k, v in group_owners.items()}
        self._authorised_domains = {d.strip().lower() for d in authorised_domains}
        self._require_auth_pass = require_auth_pass

    def authorise(self, from_address: str, auth_signals: AuthSignals) -> SenderAuthResult:
        normalised = _normalise_email(from_address)
        if normalised is None:
            return SenderAuthResult(
                ok=False,
                user_id=None,
                sender_email=from_address,
                reason=AuthResultReason.MALFORMED_SENDER,
            )

        # A failing/missing SPF+DKIM/DMARC verdict means even the claimed domain can't be
        # trusted, so this is checked before anything else - including group_owners
        # membership, since a spoofed From: header could otherwise impersonate a real owner.
        if self._require_auth_pass and not self._auth_pass(auth_signals):
            return SenderAuthResult(
                ok=False,
                user_id=None,
                sender_email=normalised,
                reason=AuthResultReason.UNAUTHENTICATED,
            )

        if normalised in self._group_owners:
            return SenderAuthResult(
                ok=True,
                user_id=self._group_owners[normalised],
                sender_email=normalised,
                reason=AuthResultReason.AUTHORISED,
            )

        domain = normalised.rsplit("@", 1)[-1]
        if domain in self._authorised_domains:
            return SenderAuthResult(
                ok=False,
                user_id=None,
                sender_email=normalised,
                reason=AuthResultReason.UNRECOGNISED_IN_DOMAIN,
            )

        return SenderAuthResult(
            ok=False,
            user_id=None,
            sender_email=normalised,
            reason=AuthResultReason.UNAUTHORISED_EXTERNAL,
        )

    @staticmethod
    def _auth_pass(signals: AuthSignals) -> bool:
        dmarc_pass = bool(signals.dmarc and signals.dmarc.lower() == "pass")
        spf_and_dkim_pass = bool(
            signals.spf
            and signals.spf.lower() == "pass"
            and signals.dkim
            and signals.dkim.lower() == "pass"
        )
        return dmarc_pass or spf_and_dkim_pass


def _normalise_email(address: str) -> Optional[str]:
    if not address:
        return None
    candidate = address.strip().lower()
    if not _EMAIL_RE.match(candidate):
        return None
    return candidate
