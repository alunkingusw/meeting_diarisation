from datetime import datetime, timezone

from app.meeting_reports import next_run


def test_next_run_is_following_sunday_night():
    saturday = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)
    assert next_run(saturday, 6, 22, 0) == datetime(2026, 10, 4, 22, tzinfo=timezone.utc)


def test_next_run_rolls_to_next_week_once_passed():
    sunday_late = datetime(2026, 10, 4, 22, 0, 1, tzinfo=timezone.utc)
    assert next_run(sunday_late, 6, 22, 0) == datetime(2026, 10, 11, 22, tzinfo=timezone.utc)
