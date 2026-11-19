"""Checks on an uploaded file before it is accepted (AMG-SR-006).

1. The declared content type must be an audio or video type (or a generic binary type).
2. The first bytes (the file signature) must match the file extension, so a text file renamed
   to .mp3 or a program renamed to .wav is refused.
3. PyAV must be able to open the file and find an audio stream.
4. If ClamAV is installed (``clamscan`` on the PATH, or CLAMSCAN_PATH), the file is scanned
   and an infected file is refused. When ClamAV is not installed this step is skipped and
   ``virus_scanner_available()`` says so.
Size limits and random file names are handled by the upload routes themselves.
Set AUDIO_PREVALIDATE=false to skip all of these checks.
"""
import os
import shutil
import subprocess
from typing import Optional


class AudioCheckError(Exception):
    """The file is not acceptable audio."""


MESSAGE = "This file could not be read as audio. Upload a valid MP3, WAV, M4A or MP4 recording."
INFECTED = "This file was rejected by the virus scan."
ALLOWED_MIME_PREFIXES = ("audio/", "video/mp4", "video/webm", "video/ogg")
GENERIC_MIME = {"application/octet-stream", "application/ogg", ""}


def _signature_ok(head: bytes, extension: str) -> bool:
    ext = extension.lower().lstrip(".")
    if ext == "wav":
        return head[:4] == b"RIFF" and head[8:12] == b"WAVE"
    if ext == "mp3":
        return head[:3] == b"ID3" or (len(head) > 1 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0)
    if ext in {"m4a", "mp4"}:
        return head[4:8] == b"ftyp"
    if ext == "ogg":
        return head[:4] == b"OggS"
    if ext == "webm":
        return head[:4] == b"\x1a\x45\xdf\xa3"
    return False


def _scanner() -> Optional[str]:
    return os.getenv("CLAMSCAN_PATH") or shutil.which("clamscan")


def virus_scanner_available() -> bool:
    return _scanner() is not None


def _scan(path: str) -> None:
    scanner = _scanner()
    if scanner is None:
        return
    result = subprocess.run([scanner, "--no-summary", path], capture_output=True, timeout=120)
    if result.returncode == 1:        # clamscan: 1 = virus found
        raise AudioCheckError(INFECTED)


def check_audio_file(path: str, content_type: Optional[str] = None, extension: Optional[str] = None) -> None:
    if os.getenv("AUDIO_PREVALIDATE", "true").strip().lower() in {"0", "false", "no", "off"}:
        return

    if content_type is not None:
        mime = content_type.split(";")[0].strip().lower()
        if mime not in GENERIC_MIME and not mime.startswith(ALLOWED_MIME_PREFIXES):
            raise AudioCheckError(MESSAGE)

    ext = extension or os.path.splitext(path)[1]
    with open(path, "rb") as f:
        head = f.read(16)
    if not _signature_ok(head, ext):
        raise AudioCheckError(MESSAGE)

    try:
        import av  # PyAV is already a dependency of faster-whisper
    except ImportError:  # cannot look inside the file; processing will still report a bad file
        av = None
    if av is not None:
        try:
            with av.open(path) as container:
                if not container.streams.audio:
                    raise AudioCheckError(MESSAGE)
        except AudioCheckError:
            raise
        except Exception as exc:  # av raises several error types for unreadable input
            raise AudioCheckError(MESSAGE) from exc

    _scan(path)
