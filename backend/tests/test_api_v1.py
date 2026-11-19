import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import api_v1, jobs
from app.database import Base, get_db
from app.main import app
from app.models import AudioDB, MeetingDB, MinutesDB
from app.transcription import AudioPreprocessingError, TranscriptionFailedError

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

LLM_RESULT = {
    "engine": "llm",
    "title": "Model title",
    "summary": "The team planned the demo.",
    "participants": ["Ravi"],
    "topics": [{"title": "Editor", "summary": "Needs work", "start_time": 14.0}],
    "decision_details": [{"decision": "Use a pre-recorded demo", "context": "Safer"}],
    "action_item_details": [{"task": "Finish the editor", "owner": "Ravi", "deadline": "Wednesday"}],
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(api_v1, "AUDIO_UPLOAD_DIR", tmp_path)
    submitted = []
    monkeypatch.setattr(jobs, "submit", lambda meeting_id, *a, **k: submitted.append(meeting_id))
    jobs._status.clear()

    test_client = TestClient(app)
    test_client.submitted = submitted
    yield test_client

    if previous is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = previous
    Base.metadata.drop_all(bind=engine)


def make_meeting(client, **overrides):
    body = {
        "title": "Sprint sync",
        "datetime": "2026-11-01T10:00",
        "agenda": "Demo plan",
        "language": "en",
        "attendees": [
            {"name": "Ravi Kumar", "email": "r@example.com"},
            {"name": " ", "email": ""},
        ],
    }
    body.update(overrides)
    return client.post("/api/v1/meetings", json=body)


def new_meeting_id(client):
    return make_meeting(client).json()["meetingId"]


def upload(client, meeting_id, name="meeting.wav", data=b"fake audio"):
    return client.post(
        f"/api/v1/meetings/{meeting_id}/audio",
        files={"file": (name, data, "audio/wav")},
    )


def run_fake_job(client, monkeypatch, meeting_id):
    upload(client, meeting_id)
    segments = [{"start": 1.0, "end": 3.0, "text": "Ravi will finish it by Wednesday."}]
    monkeypatch.setattr(
        jobs, "transcribe_audio",
        lambda path, **kwargs: {"text": "Ravi will finish it by Wednesday.", "language": "en", "segments": segments},
    )
    seen = {}

    def fake_generate(text, segments=None, progress=None):
        seen["segments"] = segments
        if progress:
            progress(1, 1)
        return LLM_RESULT

    monkeypatch.setattr(jobs, "generate_minutes", fake_generate)
    jobs.run_job(meeting_id, session_factory=TestSession)
    return seen


# ---------------------------------------------------------------------------
# 1. Meeting CRUD and Retrieval
# ---------------------------------------------------------------------------
def test_create_meeting_returns_meeting_id(client):
    response = make_meeting(client)
    assert response.status_code == 201
    data = response.json()
    assert data["meetingId"]
    assert data["id"] == data["meetingId"]
    assert data["status"] == "created"


def test_create_meeting_rejects_a_missing_or_blank_title(client):
    assert client.post("/api/v1/meetings", json={"agenda": "x"}).status_code == 400
    assert make_meeting(client, title="").status_code == 400
    assert make_meeting(client, title="   ").status_code == 400


def test_list_meetings(client):
    make_meeting(client, title="Meeting Alpha")
    make_meeting(client, title="Meeting Beta")
    response = client.get("/api/v1/meetings")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 2
    titles = [m["title"] for m in items]
    assert "Meeting Alpha" in titles
    assert "Meeting Beta" in titles


def test_get_meeting_by_id(client):
    meeting_id = new_meeting_id(client)
    response = client.get(f"/api/v1/meetings/{meeting_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == meeting_id
    assert data["title"] == "Sprint sync"
    assert data["status"] == "created"


def test_get_missing_meeting_returns_404(client):
    response = client.get("/api/v1/meetings/non-existent-uuid")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# 2. Audio Upload & Validation
# ---------------------------------------------------------------------------
def test_upload_starts_a_job(client):
    meeting_id = new_meeting_id(client)
    assert upload(client, meeting_id).status_code == 201
    assert client.submitted == [meeting_id]


def test_upload_errors(client):
    meeting_id = new_meeting_id(client)
    assert upload(client, "unknown").status_code == 404
    assert upload(client, meeting_id, name="notes.txt").status_code == 415
    assert upload(client, meeting_id, data=b"").status_code == 400
    assert client.submitted == []


def test_oversized_upload_is_rejected_and_cleaned_up(client, monkeypatch, tmp_path):
    monkeypatch.setattr(api_v1, "MAX_AUDIO_BYTES", 10)
    meeting_id = new_meeting_id(client)
    assert upload(client, meeting_id, data=b"x" * 11).status_code == 413
    assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------------------------
# 3. Status Reporting & Job Lifecycle
# ---------------------------------------------------------------------------
def test_status_before_any_audio(client):
    meeting_id = new_meeting_id(client)
    body = client.get(f"/api/v1/meetings/{meeting_id}/status").json()
    assert body["status"] == "QUEUED"


def test_status_for_an_unknown_meeting(client):
    assert client.get("/api/v1/meetings/nope/status").status_code == 404


def test_status_reports_the_running_job(client):
    meeting_id = new_meeting_id(client)
    upload(client, meeting_id)
    jobs.set_status(meeting_id, "ANALYSING", "Finding decisions and action items", 60)
    body = client.get(f"/api/v1/meetings/{meeting_id}/status").json()
    assert body == {"status": "ANALYSING", "stage": "Finding decisions and action items", "progress": 60}


def test_status_after_a_restart_offers_a_retry(client):
    meeting_id = new_meeting_id(client)
    upload(client, meeting_id)  # job state in memory is cleared, mimicking restart
    body = client.get(f"/api/v1/meetings/{meeting_id}/status").json()
    assert body["status"] == "FAILED"
    assert body["error"]


def test_job_creates_minutes(client, monkeypatch):
    meeting_id = new_meeting_id(client)
    seen = run_fake_job(client, monkeypatch, meeting_id)

    assert client.get(f"/api/v1/meetings/{meeting_id}/status").json()["status"] == "READY"
    minutes = client.get(f"/api/v1/meetings/{meeting_id}/minutes").json()
    assert minutes["title"] == "Sprint sync"
    assert minutes["actionItems"][0]["owner"] == "Ravi Kumar"
    assert minutes["actionItems"][0]["due"] == "2026-11-04"
    assert seen["segments"]


def test_job_failure_is_reported(client, monkeypatch):
    meeting_id = new_meeting_id(client)
    upload(client, meeting_id)

    def boom(path, **kwargs):
        raise TranscriptionFailedError("Could not decode audio file.")

    monkeypatch.setattr(jobs, "transcribe_audio", boom)
    jobs.run_job(meeting_id, session_factory=TestSession)

    body = client.get(f"/api/v1/meetings/{meeting_id}/status").json()
    assert body["status"] == "FAILED"
    assert "decode" in body["error"]
    assert client.get(f"/api/v1/meetings/{meeting_id}/minutes").status_code == 404


def test_recording_without_speech_fails_politely(client, monkeypatch):
    meeting_id = new_meeting_id(client)
    upload(client, meeting_id)
    monkeypatch.setattr(jobs, "transcribe_audio", lambda path, **kwargs: {"text": "  ", "segments": []})
    jobs.run_job(meeting_id, session_factory=TestSession)
    body = client.get(f"/api/v1/meetings/{meeting_id}/status").json()
    assert body["status"] == "FAILED"
    assert "speech" in body["error"]


# ---------------------------------------------------------------------------
# 4. Processing & Retry Endpoints
# ---------------------------------------------------------------------------
def test_process_endpoint_success(client):
    meeting_id = new_meeting_id(client)
    upload(client, meeting_id)
    response = client.post(f"/api/v1/meetings/{meeting_id}/process")
    assert response.status_code == 202
    assert response.json()["status"] == "QUEUED"


def test_process_endpoint_missing_meeting_or_audio(client):
    assert client.post("/api/v1/meetings/nope/process").status_code == 404
    meeting_id = new_meeting_id(client)
    res = client.post(f"/api/v1/meetings/{meeting_id}/process")
    assert res.status_code == 404
    assert res.json()["code"] == "NO_AUDIO"


def test_retry_endpoint_success(client):
    meeting_id = new_meeting_id(client)
    upload(client, meeting_id)
    response = client.post(f"/api/v1/meetings/{meeting_id}/retry")
    assert response.status_code == 202
    assert response.json()["status"] == "queued"


def test_retry_endpoint_missing_meeting_or_audio(client):
    assert client.post("/api/v1/meetings/nope/retry").status_code == 404
    meeting_id = new_meeting_id(client)
    res = client.post(f"/api/v1/meetings/{meeting_id}/retry")
    assert res.status_code == 400
    assert res.json()["code"] == "NO_AUDIO"


# ---------------------------------------------------------------------------
# 5. Minutes Retrieval, Editing & Versioning
# ---------------------------------------------------------------------------
def test_minutes_not_ready(client):
    meeting_id = new_meeting_id(client)
    assert client.get(f"/api/v1/meetings/{meeting_id}/minutes").status_code == 404


def test_saving_minutes_bumps_the_version(client, monkeypatch):
    meeting_id = new_meeting_id(client)
    run_fake_job(client, monkeypatch, meeting_id)

    minutes = client.get(f"/api/v1/meetings/{meeting_id}/minutes").json()
    assert minutes["version"] == 1
    minutes["title"] = "Edited"

    saved = client.put(f"/api/v1/minutes/{meeting_id}", json={"content": minutes})
    assert saved.json() == {"version": 2}
    again = client.get(f"/api/v1/meetings/{meeting_id}/minutes").json()
    assert again["title"] == "Edited"
    assert again["version"] == 2


def test_saving_minutes_via_nested_meetings_endpoint(client, monkeypatch):
    meeting_id = new_meeting_id(client)
    run_fake_job(client, monkeypatch, meeting_id)

    minutes = client.get(f"/api/v1/meetings/{meeting_id}/minutes").json()
    minutes["title"] = "Nested Update"

    saved = client.put(f"/api/v1/meetings/{meeting_id}/minutes", json={"content": minutes})
    assert saved.status_code == 200
    assert saved.json()["version"] == 2


def test_saving_minutes_version_conflict_rejection(client, monkeypatch):
    meeting_id = new_meeting_id(client)
    run_fake_job(client, monkeypatch, meeting_id)

    minutes = client.get(f"/api/v1/meetings/{meeting_id}/minutes").json()
    minutes["version"] = 999  # Out of sync with current version 1
    response = client.put(f"/api/v1/meetings/{meeting_id}/minutes", json={"content": minutes})
    assert response.status_code == 409
    assert response.json()["code"] == "CONFLICT"


def test_saving_needs_content_and_a_known_meeting(client):
    meeting_id = new_meeting_id(client)
    assert client.put(f"/api/v1/minutes/{meeting_id}", json={}).status_code == 400
    assert client.put("/api/v1/minutes/nope", json={"content": {}}).status_code == 404


def test_rows_from_the_older_transcribe_route_are_converted(client):
    meeting_id = new_meeting_id(client)
    old = {
        "summary": "x",
        "key_discussions": ["We met."],
        "decisions": ["We decided to ship."],
        "action_items": ["Ravi will finish it."],
        "transcript": "x",
    }
    db = TestSession()
    db.add(MinutesDB(id="m1", meeting_id=meeting_id, transcript_id="t1", content_json=json.dumps(old)))
    db.commit()
    db.close()

    minutes = client.get(f"/api/v1/meetings/{meeting_id}/minutes").json()
    assert minutes["decisions"][0]["statement"] == "We decided to ship."


# ---------------------------------------------------------------------------
# 6. Export Endpoints
# ---------------------------------------------------------------------------
def test_export_markdown(client, monkeypatch):
    meeting_id = new_meeting_id(client)
    run_fake_job(client, monkeypatch, meeting_id)

    response = client.post(f"/api/v1/meetings/{meeting_id}/export", json={"format": "md"})
    assert response.status_code == 200
    assert "text/markdown" in response.headers["content-type"]
    assert "attachment;" in response.headers["content-disposition"]
    text = response.text
    assert "# Minutes of Meeting:" in text
    assert "Sprint sync" in text


def test_export_docx(client, monkeypatch):
    meeting_id = new_meeting_id(client)
    run_fake_job(client, monkeypatch, meeting_id)

    response = client.post(f"/api/v1/meetings/{meeting_id}/export", json={"format": "docx"})
    assert response.status_code == 200
    assert "application/vnd.openxmlformats" in response.headers["content-type"]
    assert response.content[:2] == b"PK"  # Zip archive header for docx


def test_export_pdf(client, monkeypatch):
    meeting_id = new_meeting_id(client)
    run_fake_job(client, monkeypatch, meeting_id)

    response = client.post(f"/api/v1/meetings/{meeting_id}/export", json={"format": "pdf"})
    assert response.status_code == 200
    assert "application/pdf" in response.headers["content-type"]
    assert response.content[:4] == b"%PDF"


def test_export_invalid_format_rejected(client, monkeypatch):
    meeting_id = new_meeting_id(client)
    run_fake_job(client, monkeypatch, meeting_id)
    response = client.post(f"/api/v1/meetings/{meeting_id}/export", json={"format": "exe"})
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_FORMAT"


def test_export_before_minutes_ready_returns_404(client):
    meeting_id = new_meeting_id(client)
    response = client.post(f"/api/v1/meetings/{meeting_id}/export", json={"format": "md"})
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_READY"


# ---------------------------------------------------------------------------
# 7. Security Test Scenarios
# ---------------------------------------------------------------------------
def test_security_path_traversal_filename_neutralized(client, tmp_path):
    """TC-Sec-06-C: Filename containing path traversal sequences (../../etc/passwd)
    must not write outside the intended upload directory."""
    meeting_id = new_meeting_id(client)
    malicious_filename = "../../../exploit.wav"
    res = client.post(
        f"/api/v1/meetings/{meeting_id}/audio",
        files={"file": (malicious_filename, b"RIFFfake", "audio/wav")},
    )
    assert res.status_code == 201
    # File is saved with safe UUID name directly inside tmp_path, never outside
    stored_files = list(tmp_path.iterdir())
    assert len(stored_files) == 1
    assert stored_files[0].parent.resolve() == tmp_path.resolve()
    assert not (tmp_path.parent / "exploit.wav").exists()


def test_security_extension_spoofing_handled_by_transcription(client, monkeypatch):
    """TC-Sec-06-B: Text/script file renamed to .wav or .mp3 passes file extension
    check, but is caught gracefully during transcription without crashing backend."""
    meeting_id = new_meeting_id(client)
    # Upload text payload masquerading as .wav
    res = upload(client, meeting_id, name="malicious.wav", data=b"SELECT * FROM users; <script>alert(1)</script>")
    assert res.status_code == 201

    # Transcription attempts decoding and raises preprocessing/decoding error
    def decode_fail(path):
        raise AudioPreprocessingError("Could not decode audio stream: invalid data")

    monkeypatch.setattr(jobs, "transcribe_audio", decode_fail)
    jobs.run_job(meeting_id, session_factory=TestSession)

    status_res = client.get(f"/api/v1/meetings/{meeting_id}/status").json()
    assert status_res["status"] == "FAILED"
    assert "invalid data" in status_res["error"]


def test_security_xss_and_sql_injection_in_meeting_inputs(client):
    """TC-Sec-10: Payload containing script tags and SQL injection primitives
    stored safely as literal text without causing injection."""
    xss_title = "<script>alert('xss')</script>"
    sqli_agenda = "'; DROP TABLE meetings; --"
    res = make_meeting(client, title=xss_title, agenda=sqli_agenda)
    assert res.status_code == 201
    meeting_id = res.json()["meetingId"]

    # Verify retrieval preserves exact literal string safely
    fetch_res = client.get(f"/api/v1/meetings/{meeting_id}")
    assert fetch_res.status_code == 200
    assert fetch_res.json()["title"] == xss_title
    assert fetch_res.json()["description"] == sqli_agenda


def test_security_database_rollback_on_upload_error(client, monkeypatch):
    """Verify that an unexpected error during upload commits no partial audio records."""
    meeting_id = new_meeting_id(client)

    def failing_add(*args, **kwargs):
        raise RuntimeError("Database connection interrupted")

    # Monkeypatch AudioDB.__init__ to simulate failure during record creation
    # TestClient with raise_server_exceptions=False receives HTTP 500 instead of re-raising
    no_raise_client = TestClient(app, raise_server_exceptions=False)
    with monkeypatch.context() as m:
        m.setattr(AudioDB, "__init__", failing_add)
        res = no_raise_client.post(
            f"/api/v1/meetings/{meeting_id}/audio",
            files={"file": ("test.wav", b"RIFFdummy", "audio/wav")},
        )
        assert res.status_code == 500

    # Ensure no audio record was committed
    db = TestSession()
    assert db.query(AudioDB).filter(AudioDB.meeting_id == meeting_id).first() is None
    db.close()
