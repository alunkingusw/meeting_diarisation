from app.auth.authorisation import AuthResultReason, AuthSignals, SenderAuthoriser

GROUP_OWNERS = {"alice@university.ac.uk": 12, "bob@university.ac.uk": 7}
DOMAINS = ["university.ac.uk"]

PASS = AuthSignals(spf="pass", dkim="pass", dmarc="pass")
FAIL = AuthSignals(spf="fail", dkim="fail", dmarc="fail")
MISSING = AuthSignals()


def _authoriser(require_auth_pass=True):
    return SenderAuthoriser(GROUP_OWNERS, DOMAINS, require_auth_pass=require_auth_pass)


def test_authorised_owner_with_passing_signals():
    result = _authoriser().authorise("alice@university.ac.uk", PASS)
    assert result.ok is True
    assert result.user_id == 12
    assert result.reason == AuthResultReason.AUTHORISED


def test_authorisation_is_case_insensitive():
    result = _authoriser().authorise("Alice@University.AC.UK", PASS)
    assert result.ok is True
    assert result.user_id == 12


def test_dmarc_pass_alone_is_sufficient():
    result = _authoriser().authorise(
        "alice@university.ac.uk", AuthSignals(spf="fail", dkim="fail", dmarc="pass")
    )
    assert result.ok is True


def test_spf_and_dkim_pass_without_dmarc_is_sufficient():
    result = _authoriser().authorise(
        "alice@university.ac.uk", AuthSignals(spf="pass", dkim="pass", dmarc=None)
    )
    assert result.ok is True


def test_in_domain_but_not_a_registered_owner_is_unrecognised():
    result = _authoriser().authorise("carol@university.ac.uk", PASS)
    assert result.ok is False
    assert result.user_id is None
    assert result.reason == AuthResultReason.UNRECOGNISED_IN_DOMAIN


def test_outside_domain_and_not_a_registered_owner_is_external():
    result = _authoriser().authorise("mallory@evil.example", PASS)
    assert result.ok is False
    assert result.reason == AuthResultReason.UNAUTHORISED_EXTERNAL


def test_failing_auth_signals_are_unauthenticated_even_for_a_registered_owner():
    # A spoofed From: header claiming to be a real owner must not be trusted just because
    # the address string matches - this is exactly the case the auth-signal check defends.
    result = _authoriser().authorise("alice@university.ac.uk", FAIL)
    assert result.ok is False
    assert result.reason == AuthResultReason.UNAUTHENTICATED


def test_missing_auth_signals_treated_as_unauthenticated_when_required():
    result = _authoriser().authorise("alice@university.ac.uk", MISSING)
    assert result.ok is False
    assert result.reason == AuthResultReason.UNAUTHENTICATED


def test_require_auth_pass_false_allows_bypass():
    result = _authoriser(require_auth_pass=False).authorise("alice@university.ac.uk", MISSING)
    assert result.ok is True
    assert result.reason == AuthResultReason.AUTHORISED


def test_require_auth_pass_false_still_distinguishes_domain_tiers():
    authoriser = _authoriser(require_auth_pass=False)
    in_domain = authoriser.authorise("carol@university.ac.uk", MISSING)
    external = authoriser.authorise("mallory@evil.example", MISSING)
    assert in_domain.reason == AuthResultReason.UNRECOGNISED_IN_DOMAIN
    assert external.reason == AuthResultReason.UNAUTHORISED_EXTERNAL


def test_malformed_sender_address():
    result = _authoriser().authorise("not-an-email-address", PASS)
    assert result.ok is False
    assert result.reason == AuthResultReason.MALFORMED_SENDER


def test_empty_sender_address():
    result = _authoriser().authorise("", PASS)
    assert result.ok is False
    assert result.reason == AuthResultReason.MALFORMED_SENDER
