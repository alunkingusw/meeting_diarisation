"""Parser for the WEBVTT transcripts accepted via email.

Cue structure is parsed by webvtt-py. Speaker extraction accepts both Teams
voice spans (`<v Speaker>text</v>`) and the backend's `Speaker: text` format.
Malformed individual cues remain warnings, but a file with zero cues is invalid.

Meeting-date convention: a WEBVTT NOTE cue whose body starts with "meeting-date:" (case
insensitive), e.g. `NOTE meeting-date: 2026-08-11`. The first such NOTE found wins if more than
one is present. This is documented in the README for anyone producing these transcripts.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

from dateutil import parser as dateutil_parser
from webvtt import WebVTT
from webvtt.errors import MalformedCaptionError, MalformedFileError

WEBVTT_HEADER_RE = re.compile(r"^WEBVTT\b")
NOTE_DATE_RE = re.compile(r"^meeting-date:\s*(?P<value>.+)$", re.IGNORECASE)
CUE_SPEAKER_RE = re.compile(r"^(?P<speaker>[^:\n]{1,100}):\s?(?P<text>.*)$")

_BLOCK_SPLIT_RE = re.compile(r"\r?\n\r?\n+")


class VttParseError(Exception):
    """Raised when the file isn't a usable VTT transcript at all (not merely ambiguous)."""


@dataclass
class ParsedVtt:
    speakers: list[str] = field(default_factory=list)
    meeting_date: Optional[datetime] = None
    meeting_date_source: Optional[str] = None  # "vtt_note" when set
    cue_count: int = 0
    warnings: list[str] = field(default_factory=list)


def parse_vtt(path: Union[str, Path]) -> ParsedVtt:
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    stripped = text.strip()
    if not WEBVTT_HEADER_RE.match(stripped):
        raise VttParseError("File does not start with a WEBVTT header")

    try:
        webvtt = WebVTT.from_string(stripped)
    except (MalformedCaptionError, MalformedFileError) as exc:
        raise VttParseError(f"Could not parse WEBVTT content: {exc}") from exc

    blocks = _BLOCK_SPLIT_RE.split(stripped)
    blocks = blocks[1:] if blocks else []  # drop the WEBVTT header block itself

    result = ParsedVtt()
    seen_speakers: dict[str, None] = {}

    for block in blocks:
        lines = [ln for ln in block.splitlines() if ln.strip() != ""]
        if not lines:
            continue

        if lines[0].strip().upper().startswith("NOTE"):
            _handle_note_block(lines, result)

    for caption in webvtt.captions:
        result.cue_count += 1
        speaker = caption.voice
        cue_text = " ".join(caption.text.split())

        if not speaker:
            match = CUE_SPEAKER_RE.match(cue_text)
            if match:
                speaker = match.group("speaker").strip()

        if not speaker:
            result.warnings.append(
                f"Cue without a recognisable speaker label: {cue_text[:80]!r}"
            )
            continue

        if speaker not in seen_speakers:
            seen_speakers[speaker] = None

    result.speakers = list(seen_speakers.keys())

    if result.cue_count == 0:
        raise VttParseError("No cues found in VTT file")

    return result


def _handle_note_block(lines: list[str], result: ParsedVtt) -> None:
    if result.meeting_date is not None:
        return  # first matching NOTE wins

    first_line = lines[0].strip()
    body_lines = [first_line[4:].strip()] if len(first_line) > 4 else []
    body_lines += [ln.strip() for ln in lines[1:]]
    body = " ".join(b for b in body_lines if b)

    date_match = NOTE_DATE_RE.match(body)
    if not date_match:
        return

    raw_value = date_match.group("value").strip()
    try:
        parsed = dateutil_parser.parse(raw_value)
    except (ValueError, OverflowError, dateutil_parser.ParserError):
        result.warnings.append(f"Could not parse meeting-date NOTE value: {raw_value!r}")
        return

    result.meeting_date = parsed
    result.meeting_date_source = "vtt_note"
