"""
Core VTT parsing utilities shared by verification and chunking.

This is the single source of truth for extracting (speaker, text, timestamp)
from a raw cue block, supporting two speaker formats:

  - Voice tag:    <v Speaker Name>text</v>
  - Label prefix: "SPEAKER_00: text"  or  "Alice Smith: text"

Both verify_vtt and the chunk-builder use these same functions, so
"verified as valid" and "successfully extracted" can never disagree.
"""
import re
from typing import Optional

from .models import Cue

TIMESTAMP_RE = re.compile(r'(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})')
VOICE_TAG_RE = re.compile(r'<v\s+([^>]+)>\s*(.*?)(?:</v>)?\s*$', re.DOTALL)
# Label prefix: a short leading label followed immediately by a colon.
# The 50-char cap and single-line restriction keep this from false-matching
# ordinary sentences ("Note: this is important") or timestamp lines.
LABEL_PREFIX_RE = re.compile(r'^\s*([A-Za-z0-9_][A-Za-z0-9_ ]{0,49}):\s*(.+)$')


def split_cue_blocks(raw_text: str) -> list[str]:
    """Split a VTT file's contents into cue blocks (blank-line separated),
    keeping only blocks that contain a timestamp line."""
    blocks = re.split(r'\n\s*\n', raw_text)
    return [b for b in blocks if TIMESTAMP_RE.search(b)]


def extract_timestamp(cue_block: str) -> Optional[tuple[str, str]]:
    """Return (start_ts, end_ts) strings from a cue block, or None."""
    match = TIMESTAMP_RE.search(cue_block)
    if not match:
        return None
    return match.group(1), match.group(2)


def extract_speaker_and_text(cue_block: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Given a raw VTT cue block, extract (speaker, text, format_used).
    format_used is "voice_tag", "label_prefix", or None if extraction failed.
    Voice tag is tried first (unambiguous); label prefix is the fallback.
    """
    lines = cue_block.strip().splitlines()
    # A bare numeric line is the optional WebVTT cue identifier (e.g. "1", "2", ...) that
    # commonly precedes the timestamp line, not part of the spoken text - skip it the same way
    # the timestamp line itself is skipped, or it gets mistaken for the speaker-prefix line.
    text_lines = [
        l for l in lines if not TIMESTAMP_RE.search(l) and l.strip() and not l.strip().isdigit()
    ]
    if not text_lines:
        return None, None, None

    body = "\n".join(text_lines).strip()

    match = VOICE_TAG_RE.search(body)
    if match:
        speaker = match.group(1).strip()
        text = match.group(2).strip()
        if speaker and text:
            return speaker, text, "voice_tag"

    first_line = text_lines[0]
    match = LABEL_PREFIX_RE.match(first_line)
    if match:
        speaker = match.group(1).strip()
        rest_of_first = match.group(2).strip()
        remaining = text_lines[1:]
        text = "\n".join([rest_of_first] + remaining).strip()
        if speaker and text:
            return speaker, text, "label_prefix"

    return None, None, None


def parse_vtt_cues(raw_text: str) -> list[Cue]:
    """Full parse of a VTT file's text into a list of Cue objects.
    Cues that don't yield a speaker/text/timestamp are silently skipped —
    run verify_vtt() on the file first to catch that at the file level
    rather than discovering missing cues here."""
    cues = []
    for idx, block in enumerate(split_cue_blocks(raw_text)):
        ts = extract_timestamp(block)
        speaker, text, fmt = extract_speaker_and_text(block)
        if ts and speaker and text:
            cues.append(Cue(
                index=idx,
                speaker=speaker,
                text=text,
                start_ts=ts[0],
                end_ts=ts[1],
                format=fmt,
            ))
    return cues
