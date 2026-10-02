from app.auth.authorisation import AuthResultReason, AuthSignals, SenderAuthoriser

GROUP_OWNERS = {"alice@university.ac.uk": 12, "bob@university.ac.uk": 7}

PASS = AuthSignals(spf="pass", dkim="pass", dmarc="pass")
FAIL = AuthSignals(spf="fail", dkim="fail", dmarc="fail")
MISSING = AuthSignals()


def _authoriser(require_auth_pass=True):
    return SenderAuthoriser(GROUP_OWNERS, require_auth_pass=require_auth_pass)


def test_authorised_owner_with_passing_signals():
    result = _authoriser().authorise("alice@university.ac.uk", PASS)
    assert result.ok is True
    assert result.user_id == 12
    assert result.reason == AuthResultReason.AUTHORISED


def test_registered_group_member_is_authorised_with_member_identity():
    authoriser = SenderAuthoriser(
        GROUP_OWNERS,
        group_members={"carol@university.ac.uk": [21, 22]},
    )

    result = authoriser.authorise("carol@university.ac.uk", PASS)

    assert result.ok is True
    assert result.user_id is None
    assert result.group_member_ids == (21, 22)
    assert result.reason == AuthResultReason.GROUP_MEMBER


def test_registered_user_takes_precedence_over_group_member():
    authoriser = SenderAuthoriser(
        GROUP_OWNERS,
        group_members={"alice@university.ac.uk": [21]},
    )

    result = authoriser.authorise("alice@university.ac.uk", PASS)

    assert result.reason == AuthResultReason.AUTHORISED
    assert result.user_id == 12
    assert result.group_member_ids == ()


def test_group_member_address_still_requires_passing_authentication():
    authoriser = SenderAuthoriser(
        GROUP_OWNERS,
        group_members={"carol@university.ac.uk": [21]},
    )

    result = authoriser.authorise("carol@university.ac.uk", FAIL)

    assert result.reason == AuthResultReason.UNAUTHENTICATED


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


def test_unregistered_sender_is_not_authorised_even_on_a_familiar_domain():
    result = _authoriser().authorise("carol@university.ac.uk", PASS)
    assert result.ok is False
    assert result.user_id is None
    assert result.reason == AuthResultReason.UNREGISTERED


def test_unregistered_sender_on_an_unrelated_domain_is_also_unregistered():
    result = _authoriser().authorise("mallory@evil.example", PASS)
    assert result.ok is False
    assert result.reason == AuthResultReason.UNREGISTERED


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


def test_require_auth_pass_false_does_not_make_unregistered_senders_authorised():
    result = _authoriser(require_auth_pass=False).authorise("carol@university.ac.uk", MISSING)
    assert result.reason == AuthResultReason.UNREGISTERED


def test_malformed_sender_address():
    result = _authoriser().authorise("not-an-email-address", PASS)
    assert result.ok is False
    assert result.reason == AuthResultReason.MALFORMED_SENDER


def test_empty_sender_address():
    result = _authoriser().authorise("", PASS)
    assert result.ok is False
    assert result.reason == AuthResultReason.MALFORMED_SENDER
