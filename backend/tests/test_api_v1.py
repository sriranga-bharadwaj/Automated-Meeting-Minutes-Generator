import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import api_v1, jobs
from app.database import Base, get_db
from app.main import app
from app.models import MinutesDB
from app.transcription import TranscriptionFailedError

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
        lambda path: {"text": "Ravi will finish it by Wednesday.", "language": "en", "segments": segments},
    )
    seen = {}

    def fake_generate(text, segments=None, progress=None):
        seen["segments"] = segments
        progress(1, 1)
        return LLM_RESULT

    monkeypatch.setattr(jobs, "generate_minutes", fake_generate)
    jobs.run_job(meeting_id, session_factory=TestSession)
    return seen


def test_create_meeting_returns_meeting_id(client):
    response = make_meeting(client)
    assert response.status_code == 201
    assert response.json()["meetingId"]


def test_create_meeting_rejects_a_missing_or_blank_title(client):
    assert client.post("/api/v1/meetings", json={"agenda": "x"}).status_code == 400
    assert make_meeting(client, title="").status_code == 400
    assert make_meeting(client, title="   ").status_code == 400


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
    upload(client, meeting_id)                        # job state is empty, as after a restart
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
    assert seen["segments"]                           # timestamps reach the generator


def test_job_failure_is_reported(client, monkeypatch):
    meeting_id = new_meeting_id(client)
    upload(client, meeting_id)

    def boom(path):
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
    monkeypatch.setattr(jobs, "transcribe_audio", lambda path: {"text": "  ", "segments": []})
    jobs.run_job(meeting_id, session_factory=TestSession)
    body = client.get(f"/api/v1/meetings/{meeting_id}/status").json()
    assert body["status"] == "FAILED"
    assert "speech" in body["error"]


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