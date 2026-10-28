"""Speech-to-text pipeline for the Automated Meeting Minutes Generator.

Public interface (used by ``app.main``)::

    transcribe_audio(audio_path: str) -> dict

The returned dict has this shape::

    {
        "text": "full transcript ...",
        "language": "en",
        "language_probability": 0.99,
        "duration": 63.2,                 # seconds of audio
        "segments": [
            {"start": 0.0, "end": 4.2, "text": "..."},
            ...
        ],
    }

Pipeline:
    1. Validate the file (exists, non-empty, supported extension).
    2. Preprocess with FFmpeg to 16 kHz mono WAV (what Whisper expects).
       This also handles containers such as .mp4 / .webm / .m4a uniformly
       and rejects corrupt or non-audio files early with a clear error.
    3. Transcribe with faster-whisper and return text + timestamps.

Errors are raised as subclasses of ``TranscriptionError`` so the API layer
can map them to proper HTTP status codes. ``FileNotFoundError`` is kept for
a missing file because ``app.main`` already handles it.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Formats accepted by the upload endpoint (keep in sync with app.main).
SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".webm", ".mp4"}

# Whisper model settings. Override with environment variables if needed.
MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")
DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

# Seconds to wait for FFmpeg before giving up (long meetings need headroom).
FFMPEG_TIMEOUT = int(os.getenv("FFMPEG_TIMEOUT", "600"))


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------
class TranscriptionError(Exception):
    """Base class for all transcription pipeline errors."""


class UnsupportedAudioFormatError(TranscriptionError):
    """The file extension is not one of the supported audio types."""


class AudioPreprocessingError(TranscriptionError):
    """FFmpeg is missing, or the file is corrupt / contains no audio."""


class TranscriptionFailedError(TranscriptionError):
    """The speech-to-text model failed while processing the audio."""


# --------------------------------------------------------------------------
# Model loading
# --------------------------------------------------------------------------
_model = None


def get_model():
    """Load the speech recognition model lazily (first use only)."""
    global _model

    if _model is None:
        from faster_whisper import WhisperModel

        logger.info(
            "Loading faster-whisper model '%s' (device=%s, compute_type=%s)",
            MODEL_SIZE,
            DEVICE,
            COMPUTE_TYPE,
        )
        _model = WhisperModel(
            MODEL_SIZE,
            device=DEVICE,
            compute_type=COMPUTE_TYPE,
        )

    return _model


# --------------------------------------------------------------------------
# Audio preprocessing
# --------------------------------------------------------------------------
def preprocess_audio(input_path: Path, output_path: Path) -> Path:
    """Convert any supported audio/video file to 16 kHz mono 16-bit WAV.

    Raises:
        AudioPreprocessingError: FFmpeg is not installed, timed out, or could
            not decode the file (corrupt file or no audio stream).
    """
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise AudioPreprocessingError(
            "FFmpeg is not installed or not on PATH. "
            "Install it from https://ffmpeg.org/download.html and retry."
        )

    command = [
        ffmpeg,
        "-nostdin",
        "-y",
        "-i", str(input_path),
        "-vn",                      # drop any video stream (e.g. .mp4)
        "-ac", "1",                 # mono
        "-ar", "16000",             # 16 kHz
        "-c:a", "pcm_s16le",        # 16-bit PCM WAV
        str(output_path),
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=FFMPEG_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        raise AudioPreprocessingError(
            f"FFmpeg timed out after {FFMPEG_TIMEOUT} seconds."
        ) from exc

    if result.returncode != 0:
        # Last stderr line is usually the actual reason.
        stderr_lines = [
            line for line in result.stderr.strip().splitlines() if line.strip()
        ]
        reason = stderr_lines[-1] if stderr_lines else "unknown FFmpeg error"
        raise AudioPreprocessingError(
            f"Could not decode audio file ({reason})."
        )

    if not output_path.is_file() or output_path.stat().st_size <= 44:
        # 44 bytes is just a WAV header, i.e. no audio samples at all.
        raise AudioPreprocessingError("The file contains no audio data.")

    return output_path


# --------------------------------------------------------------------------
# Main entry point
# --------------------------------------------------------------------------
def transcribe_audio(audio_path: str) -> dict:
    """Transcribe an audio file and return text with timestamped segments.

    Raises:
        FileNotFoundError: the audio file does not exist.
        UnsupportedAudioFormatError: unsupported file extension.
        AudioPreprocessingError: FFmpeg missing, or corrupt / empty audio.
        TranscriptionFailedError: the Whisper model failed.
    """
    path = Path(audio_path)

    if not path.is_file():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    extension = path.suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise UnsupportedAudioFormatError(
            f"Unsupported audio format '{extension or 'unknown'}'. "
            f"Supported formats: {supported}."
        )

    if path.stat().st_size == 0:
        raise AudioPreprocessingError("The audio file is empty.")

    with tempfile.TemporaryDirectory(prefix="ammg_audio_") as tmp_dir:
        wav_path = preprocess_audio(path, Path(tmp_dir) / "audio_16k.wav")

        try:
            model = get_model()
            segments, info = model.transcribe(
                str(wav_path),
                beam_size=5,
                vad_filter=True,
            )

            # `segments` is a generator: decoding happens while iterating,
            # so it must be consumed inside this try block.
            transcript_segments = []
            for segment in segments:
                text = segment.text.strip()
                if not text:
                    continue
                transcript_segments.append(
                    {
                        "start": round(segment.start, 2),
                        "end": round(segment.end, 2),
                        "text": text,
                    }
                )
        except TranscriptionError:
            raise
        except Exception as exc:
            logger.exception("faster-whisper transcription failed")
            raise TranscriptionFailedError(
                f"Speech-to-text failed: {type(exc).__name__}: {exc}"
            ) from exc

    full_text = " ".join(segment["text"] for segment in transcript_segments)

    return {
        "text": full_text,
        "language": info.language,
        "language_probability": round(info.language_probability, 3),
        "duration": round(info.duration, 2),
        "segments": transcript_segments,
    }


def _format_timestamp(seconds: float) -> str:
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(int(minutes), 60)
    return f"{hours:02d}:{minutes:02d}:{secs:05.2f}"


def main(argv: list[str] | None = None) -> int:
    """Command-line demo: ``python -m app.transcription meeting.mp3``."""
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(
        description="Transcribe a meeting recording to text with timestamps."
    )
    parser.add_argument("audio", help="Path to the audio file")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full result as JSON instead of a readable transcript",
    )
    args = parser.parse_args(argv)

    try:
        result = transcribe_audio(args.audio)
    except (FileNotFoundError, TranscriptionError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    print(
        f"Language: {result['language']} "
        f"(confidence {result['language_probability']}), "
        f"duration: {result['duration']}s\n"
    )
    for seg in result["segments"]:
        print(
            f"[{_format_timestamp(seg['start'])} -> "
            f"{_format_timestamp(seg['end'])}] {seg['text']}"
        )
    print(f"\nFull transcript:\n{result['text']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
