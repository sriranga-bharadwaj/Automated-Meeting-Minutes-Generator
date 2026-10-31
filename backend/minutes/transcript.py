def format_timestamp(seconds: float) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"[{h:02d}:{m:02d}:{s:02d}]"


def _get(seg, key):
    """Works for dicts and for objects with attributes (faster-whisper segments)."""
    return seg[key] if isinstance(seg, dict) else getattr(seg, key)


def segments_to_transcript(segments) -> str:
    """Turn speech-to-text segments (with .start in seconds and .text) into
    '[HH:MM:SS] text' lines, the format generate_minutes expects."""
    lines = []
    for seg in segments:
        text = _get(seg, "text").strip()
        if text:
            lines.append(f"{format_timestamp(_get(seg, 'start'))} {text}")
    return "\n".join(lines)