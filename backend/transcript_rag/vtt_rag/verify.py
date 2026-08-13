"""Pre-flight verification that a VTT file has usable speaker metadata,
before it's handed to the chunker."""
from dataclasses import dataclass, field
from pathlib import Path

from .parsing import split_cue_blocks, extract_speaker_and_text


@dataclass
class VTTVerificationResult:
    file_path: str
    is_valid: bool
    total_cues: int = 0
    cues_missing_speaker: int = 0
    unique_speakers: set = field(default_factory=set)
    formats_detected: set = field(default_factory=set)  # {"voice_tag", "label_prefix"}
    problem_cue_indices: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"File: {self.file_path}",
            f"Valid: {self.is_valid}",
            f"Total cues: {self.total_cues}",
            f"Cues missing speaker: {self.cues_missing_speaker}",
            f"Formats detected: {sorted(self.formats_detected)}",
            f"Unique speakers: {sorted(self.unique_speakers)}",
        ]
        if self.errors:
            lines.append(f"Errors: {self.errors}")
        if self.problem_cue_indices:
            lines.append(f"Problem cue indices (first 10): {self.problem_cue_indices[:10]}")
        return "\n".join(lines)


def verify_vtt(file_path: str, min_speakers: int = 2, raise_on_failure: bool = True) -> VTTVerificationResult:
    """
    Verify a VTT file has usable speaker metadata before chunking.
    Accepts either <v Speaker Name> voice tags or "SPEAKER_00: text" label
    prefixes.

    Checks:
      1. File exists, is non-empty, and starts with WEBVTT header.
      2. Contains at least one timestamp cue.
      3. Every text cue yields a speaker via one of the two supported formats.
      4. At least `min_speakers` distinct speakers are present (catches
         diarization that collapsed everyone into a single ID).

    Raises ValueError on failure if raise_on_failure=True, otherwise returns
    a VTTVerificationResult with is_valid=False and details for logging.
    """
    path = Path(file_path)
    result = VTTVerificationResult(file_path=str(path), is_valid=True)

    if not path.exists():
        result.is_valid = False
        result.errors.append("File does not exist")
        return _finalize(result, raise_on_failure)

    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        result.is_valid = False
        result.errors.append("File is empty")
        return _finalize(result, raise_on_failure)

    if not text.lstrip().startswith("WEBVTT"):
        result.is_valid = False
        result.errors.append("Missing WEBVTT header — not a valid VTT file")
        return _finalize(result, raise_on_failure)

    cue_blocks = split_cue_blocks(text)
    if not cue_blocks:
        result.is_valid = False
        result.errors.append("No timestamp cues found")
        return _finalize(result, raise_on_failure)

    result.total_cues = len(cue_blocks)

    for idx, block in enumerate(cue_blocks):
        speaker, cue_text, fmt = extract_speaker_and_text(block)
        if speaker and fmt:
            result.unique_speakers.add(speaker)
            result.formats_detected.add(fmt)
        else:
            result.cues_missing_speaker += 1
            result.problem_cue_indices.append(idx)

    if result.cues_missing_speaker > 0:
        result.is_valid = False
        result.errors.append(
            f"{result.cues_missing_speaker}/{result.total_cues} cues have no extractable "
            f"speaker (neither <v Speaker> nor 'SPEAKER: text' format matched)"
        )

    if len(result.formats_detected) > 1:
        # Not fatal — but worth surfacing, since mixed formats in one file
        # usually means something upstream is inconsistent.
        result.errors.append(
            f"Warning: mixed speaker formats detected in one file: {sorted(result.formats_detected)}"
        )

    if len(result.unique_speakers) < min_speakers:
        result.is_valid = False
        result.errors.append(
            f"Only {len(result.unique_speakers)} unique speaker(s) found, "
            f"expected at least {min_speakers} — diarization may have failed"
        )

    return _finalize(result, raise_on_failure)


def _finalize(result: VTTVerificationResult, raise_on_failure: bool) -> VTTVerificationResult:
    if not result.is_valid and raise_on_failure:
        raise ValueError(f"VTT verification failed for {result.file_path}:\n{result.summary()}")
    return result
