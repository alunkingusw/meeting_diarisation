"""Small shared helpers."""


def timestamp_to_seconds(ts: str) -> float:
    """Convert a VTT timestamp 'HH:MM:SS.mmm' to seconds as a float."""
    h, m, s = ts.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def seconds_to_timestamp(sec: float) -> str:
    """Convert seconds back to 'HH:MM:SS.mmm' VTT format."""
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"
