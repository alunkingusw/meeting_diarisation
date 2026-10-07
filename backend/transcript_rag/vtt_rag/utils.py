"""Small shared helpers."""


def timestamp_to_seconds(ts: str) -> float:
    """Convert a VTT timestamp 'HH:MM:SS.mmm' to seconds as a float."""
    h, m, s = ts.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)
