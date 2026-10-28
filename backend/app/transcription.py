
from pathlib import Path

from faster_whisper import WhisperModel


_model = None


def get_model():
    """Load the speech recognition model only when needed."""
    global _model

    if _model is None:
        _model = WhisperModel(
            "base",
            device="cpu",
            compute_type="int8",
        )

    return _model


def transcribe_audio(audio_path: str) -> dict:
    """Transcribe an audio file and return text with timestamps."""
    path = Path(audio_path)

    if not path.is_file():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    model = get_model()

    segments, info = model.transcribe(
        str(path),
        beam_size=5,
        vad_filter=True,
    )

    transcript_segments = []

    for segment in segments:
        transcript_segments.append(
            {
                "start": round(segment.start, 2),
                "end": round(segment.end, 2),
                "text": segment.text.strip(),
            }
        )

    full_text = " ".join(
        segment["text"] for segment in transcript_segments
    )

    return {
        "text": full_text,
        "language": info.language,
        "language_probability": round(info.language_probability, 3),
        "segments": transcript_segments,
    }
