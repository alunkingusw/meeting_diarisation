from datetime import datetime
from pathlib import Path

import pytest

from app.vtt.parser import VttParseError, parse_vtt

FIXTURES = Path(__file__).parent / "fixtures" / "vtt"


def test_valid_vtt_with_note_date_extracts_speakers_and_date():
    result = parse_vtt(FIXTURES / "valid_with_date.vtt")
    assert result.speakers == ["Alice", "Bob"]
    assert result.cue_count == 3
    assert result.meeting_date == datetime(2026, 8, 11)
    assert result.meeting_date_source == "vtt_note"
    assert result.warnings == []


def test_valid_vtt_without_date_has_no_meeting_date():
    result = parse_vtt(FIXTURES / "valid_no_date.vtt")
    assert result.speakers == ["SPEAKER_00", "SPEAKER_01"]
    assert result.meeting_date is None
    assert result.meeting_date_source is None


def test_malformed_cue_is_a_warning_not_a_failure():
    result = parse_vtt(FIXTURES / "malformed_cue.vtt")
    # 3 cues total, 2 with recognisable speakers, 1 flagged as a warning but still counted.
    assert result.cue_count == 3
    assert result.speakers == ["Alice", "Bob"]
    assert len(result.warnings) == 1
    assert "speaker" in result.warnings[0].lower()


def test_malformed_note_date_is_a_warning_not_a_failure():
    result = parse_vtt(FIXTURES / "malformed_date.vtt")
    assert result.meeting_date is None
    assert any("meeting-date" in w for w in result.warnings)
    assert result.cue_count == 1  # parsing still succeeds overall


def test_file_with_no_cues_at_all_raises():
    with pytest.raises(VttParseError):
        parse_vtt(FIXTURES / "no_cues.vtt")


def test_non_vtt_file_raises():
    with pytest.raises(VttParseError):
        parse_vtt(FIXTURES / "not_a_vtt.txt")


def test_missing_file_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        parse_vtt(tmp_path / "does_not_exist.vtt")
