"""Upload-time audio check (app/audio_check.py)."""
import wave

import pytest

from app.audio_check import AudioCheckError, check_audio_file


@pytest.fixture(autouse=True)
def check_on(monkeypatch):
    monkeypatch.setenv("AUDIO_PREVALIDATE", "true")


def test_real_wav_passes(tmp_path):
    path = tmp_path / "ok.wav"
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(b"\x00\x00" * 1600)
    check_audio_file(str(path))


def test_text_renamed_to_mp3_is_refused(tmp_path):
    path = tmp_path / "corrupt.mp3"
    path.write_text("this is plain text, not audio")
    with pytest.raises(AudioCheckError) as err:
        check_audio_file(str(path))
    assert "could not be read as audio" in str(err.value)


def test_check_can_be_switched_off(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIO_PREVALIDATE", "false")
    path = tmp_path / "corrupt.mp3"
    path.write_text("nope")
    check_audio_file(str(path))
