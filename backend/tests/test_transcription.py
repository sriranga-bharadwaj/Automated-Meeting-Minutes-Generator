import math
import struct
import wave
from types import SimpleNamespace

import pytest

from app import transcription
from app.transcription import (
    AudioPreprocessingError,
    TranscriptionFailedError,
    UnsupportedAudioFormatError,
    preprocess_audio,
    transcribe_audio,
)


def make_wav(path, seconds=1.0, rate=44100, channels=2):
    """Write a small sine-wave WAV file for testing."""
    frames = int(seconds * rate)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        for i in range(frames):
            sample = int(10000 * math.sin(2 * math.pi * 440 * i / rate))
            wav.writeframes(struct.pack("<h", sample) * channels)
    return path


class FakeModel:
    """Stands in for WhisperModel so tests never download a model."""

    def __init__(self, segments=None, error=None):
        self._segments = segments or []
        self._error = error
        self.received_path = None

    def transcribe(self, path, **kwargs):
        self.received_path = path
        if self._error:
            raise self._error
        info = SimpleNamespace(
            language="en", language_probability=0.98765, duration=1.0
        )
        return iter(self._segments), info


def seg(start, end, text):
    return SimpleNamespace(start=start, end=end, text=text)


# ---------------------------------------------------------------- validation
def test_missing_file_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        transcribe_audio(str(tmp_path / "nope.wav"))


def test_unsupported_extension_rejected(tmp_path):
    bad = tmp_path / "notes.txt"
    bad.write_text("not audio")
    with pytest.raises(UnsupportedAudioFormatError) as exc:
        transcribe_audio(str(bad))
    assert ".txt" in str(exc.value)


def test_empty_file_rejected(tmp_path):
    empty = tmp_path / "empty.wav"
    empty.write_bytes(b"")
    with pytest.raises(AudioPreprocessingError):
        transcribe_audio(str(empty))


def test_corrupt_audio_rejected(tmp_path):
    corrupt = tmp_path / "corrupt.mp3"
    corrupt.write_bytes(b"this is definitely not an mp3 file" * 50)
    with pytest.raises(AudioPreprocessingError):
        transcribe_audio(str(corrupt))


def test_missing_ffmpeg_gives_clear_error(tmp_path, monkeypatch):
    wav = make_wav(tmp_path / "a.wav")
    monkeypatch.setattr(transcription.shutil, "which", lambda name: None)
    with pytest.raises(AudioPreprocessingError, match="FFmpeg"):
        preprocess_audio(wav, tmp_path / "out.wav")


# ------------------------------------------------------------ preprocessing
def test_preprocess_converts_to_16k_mono(tmp_path):
    source = make_wav(tmp_path / "stereo44k.wav", rate=44100, channels=2)
    output = preprocess_audio(source, tmp_path / "out.wav")

    with wave.open(str(output), "rb") as wav:
        assert wav.getframerate() == 16000
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.getnframes() > 0


# ------------------------------------------------------------- transcription
def test_transcribe_returns_text_and_timestamps(tmp_path, monkeypatch):
    wav = make_wav(tmp_path / "meeting.wav")
    fake = FakeModel(
        segments=[
            seg(0.0, 2.345, "  Welcome everyone. "),
            seg(2.5, 5.0, "   "),  # blank segment must be dropped
            seg(5.0, 8.126, "Rahul will send the report."),
        ]
    )
    monkeypatch.setattr(transcription, "get_model", lambda: fake)

    result = transcribe_audio(str(wav))

    assert result["language"] == "en"
    assert result["language_probability"] == 0.988
    assert result["duration"] == 1.0
    assert result["segments"] == [
        {"start": 0.0, "end": 2.35, "text": "Welcome everyone."},
        {"start": 5.0, "end": 8.13, "text": "Rahul will send the report."},
    ]
    assert result["text"] == "Welcome everyone. Rahul will send the report."
    # The model must receive the preprocessed WAV, not the original file.
    assert fake.received_path != str(wav)


def test_transcribe_works_with_no_speech(tmp_path, monkeypatch):
    wav = make_wav(tmp_path / "silence.wav")
    monkeypatch.setattr(transcription, "get_model", lambda: FakeModel())

    result = transcribe_audio(str(wav))

    assert result["text"] == ""
    assert result["segments"] == []


def test_model_failure_wrapped(tmp_path, monkeypatch):
    wav = make_wav(tmp_path / "meeting.wav")
    monkeypatch.setattr(
        transcription,
        "get_model",
        lambda: FakeModel(error=RuntimeError("out of memory")),
    )
    with pytest.raises(TranscriptionFailedError, match="out of memory"):
        transcribe_audio(str(wav))
