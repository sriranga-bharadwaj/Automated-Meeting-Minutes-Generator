"""Test defaults: the older API tests send no login token and upload placeholder bytes
as audio, so login checks, the upload-time audio check and rate limiting are off, and the
hourly background loop is not started, unless a test turns them on (see test_auth.py,
test_audio_check.py, test_security.py)."""
import os

os.environ.setdefault("AUTH_REQUIRED", "false")
os.environ.setdefault("AUDIO_PREVALIDATE", "false")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("BACKGROUND_TASKS", "false")
# Fixed test keys so the tests never create key files in the backend folder.
os.environ.setdefault("AMMG_SECRET_KEY", "test-signing-key-not-for-real-use")
os.environ.setdefault("AMMG_DATA_KEY", "MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE=")  # 32 bytes
