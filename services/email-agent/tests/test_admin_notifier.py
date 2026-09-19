from pathlib import Path

from freezegun import freeze_time

from app.admin.notifier import AdminCategory, AdminNotifier
from app.jobs.store import Outbox


def _notifier(db_path: Path, admin_email="admin@uni.ac.uk", cooldown_minutes=15.0):
    return AdminNotifier(db_path, Outbox(db_path), admin_email, cooldown_minutes=cooldown_minutes)


def test_no_admin_email_configured_is_a_silent_noop(db_path: Path):
    notifier = _notifier(db_path, admin_email=None)
    sent = notifier.alert(AdminCategory.INFRASTRUCTURE, "Ollama unreachable")
    assert sent is False
    assert Outbox(db_path).pending() == []


def test_alert_is_enqueued_to_outbox(db_path: Path):
    notifier = _notifier(db_path)
    sent = notifier.alert(AdminCategory.UNAUTHORISED_SENDER, "mallory@evil.example tried to submit")
    assert sent is True
    pending = Outbox(db_path).pending()
    assert len(pending) == 1
    assert pending[0].to_email == "admin@uni.ac.uk"
    assert "mallory@evil.example" in pending[0].body_text


def test_second_alert_in_same_category_within_cooldown_is_suppressed(db_path: Path):
    notifier = _notifier(db_path, cooldown_minutes=15.0)
    with freeze_time("2026-08-11 10:00:00"):
        assert notifier.alert(AdminCategory.INFRASTRUCTURE, "Ollama down") is True
        assert notifier.alert(AdminCategory.INFRASTRUCTURE, "Ollama still down") is False
    assert len(Outbox(db_path).pending()) == 1


def test_alert_after_cooldown_elapses_is_sent_again(db_path: Path):
    notifier = _notifier(db_path, cooldown_minutes=15.0)
    with freeze_time("2026-08-11 10:00:00"):
        assert notifier.alert(AdminCategory.INFRASTRUCTURE, "Ollama down") is True
    with freeze_time("2026-08-11 10:16:00"):
        assert notifier.alert(AdminCategory.INFRASTRUCTURE, "Ollama still down") is True
    assert len(Outbox(db_path).pending()) == 2


def test_different_categories_have_independent_cooldowns(db_path: Path):
    notifier = _notifier(db_path, cooldown_minutes=15.0)
    with freeze_time("2026-08-11 10:00:00"):
        assert notifier.alert(AdminCategory.INFRASTRUCTURE, "Ollama down") is True
        assert notifier.alert(AdminCategory.LLM_PARSE_FAILURE, "Bad JSON") is True
    assert len(Outbox(db_path).pending()) == 2
