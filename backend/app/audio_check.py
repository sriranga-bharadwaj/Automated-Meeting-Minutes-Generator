"""Quick check at upload time that a file really is audio.

A text file renamed to .mp3 used to be accepted and only failed later, during processing,
with a raw ffmpeg message. This opens the file with PyAV and looks for an audio stream.
Set AUDIO_PREVALIDATE=false to skip the check.
"""
import os


class AudioCheckError(Exception):
    """The file is not readable audio."""


MESSAGE = "This file could not be read as audio. Upload a valid MP3, WAV, M4A or MP4 recording."


def check_audio_file(path: str) -> None:
    if os.getenv("AUDIO_PREVALIDATE", "true").strip().lower() in {"0", "false", "no", "off"}:
        return
    try:
        import av  # PyAV is already a dependency of faster-whisper
    except ImportError:  # cannot check without it; processing will still report a bad file
        return
    try:
        with av.open(path) as container:
            if not container.streams.audio:
                raise AudioCheckError(MESSAGE)
    except AudioCheckError:
        raise
    except Exception as exc:  # av raises several error types for unreadable input
        raise AudioCheckError(MESSAGE) from exc
