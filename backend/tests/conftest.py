"""Test defaults: the older API tests send no login token and upload placeholder bytes
as audio, so login checks and the upload-time audio check are off unless a test turns
them on (see test_auth.py and test_audio_check.py)."""
import os

os.environ.setdefault("AUTH_REQUIRED", "false")
os.environ.setdefault("AUDIO_PREVALIDATE", "false")
