"""Tests for the endpoints the web UI uses: process/status/minutes/export."""
import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import database, pipeline
from app.database import Base, get_db
from app.main import AUDIO_UPLOAD_DIR, app
from app.transcription import AudioPreprocessingError

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

FAKE_TRANSCRIPTION = {
    "text": "We decided to use a pre-recorded demo. Ravi will finish the editor by Wednesday.",
    "language": "en",
    "language_probability": 0.99,
    "duration": 10.0,
    "segments": [
        {"start": 0.0, "end": 4.0, "text": "We decided to use a pre-recorded demo."},
        {"start": 4.0, "end": 9.0, "text": "Ravi will finish the editor by Wednesday."},
    ],
}

LLM_MINUTES = {
    "engine": "llm",
    "title": "Demo planning",
    "summary": "The team planned the demo.",
    "participants": ["Ravi"],
    "topics": [{"title": "Demo", "summary": "Pre-recorded demo.", "start_time": 0.0}],
    "decision_details": [{"decision": "Use a pre-recorded demo", "context": None}],
    "action_item_details": [
        {"task": "Finish the editor", "owner": "Ravi", "deadline": "Wednesday"},
        {"task": "Book the room", "owner": None, "deadline": "before the review"},
    ],
    "key_discussions": [],
    "decisions": ["Use a pre-recorded demo"],
    "action_items": [],
    "transcript": FAKE_TRANSCRIPTION["text"],
}


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch):
    previous = app.dependency_overrides.get(get_db)

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    monkeypatch.setattr(database, "SessionLocal", Session)
    monkeypatch.setattr(pipeline, "transcribe_audio", lambda path, language=None: FAKE_TRANSCRIPTION)
    monkeypatch.setattr(pipeline, "generate_minutes", lambda text, segments=None: LLM_MINUTES)
    pipeline._JOBS.clear()
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    if previous is not None:
        app.dependency_overrides[get_db] = previous
    else:
        app.dependency_overrides.pop(get_db, None)
    for path in AUDIO_UPLOAD_DIR.glob("*.wav"):
        path.unlink(missing_ok=True)


client = TestClient(app)


def make_meeting(**extra):
    body = {"title": "Sprint review", **extra}
    response = client.post("/meetings", json=body)
    assert response.status_code == 201
    return response.json()["id"]


def upload(meeting_id):
    response = client.post(
        f"/meetings/{meeting_id}/audio",
        files={"file": ("m.wav", b"RIFFfake", "audio/wav")},
    )
    assert response.status_code == 201


def processed_meeting():
    meeting_id = make_meeting(
        datetime="2026-11-02T10:00",  # a Monday
        agenda="Demo plan",
        language="en",
        attendees=[{"name": "Ravi", "email": "ravi@example.com"}],
    )
    upload(meeting_id)
    assert client.post(f"/meetings/{meeting_id}/process").status_code == 202
    return meeting_id


# ------------------------------------------------------------------ creation
def test_create_meeting_accepts_ui_fields():
    meeting_id = make_meeting(
        datetime="2026-11-02T10:00",
        agenda="Plan",
        language="hi",
        attendees=[{"name": "Asha", "email": "asha@example.com"}],
    )
    assert client.get(f"/meetings/{meeting_id}").status_code == 200


# --------------------------------------------------------------- processing
def test_process_without_audio_is_404():
    meeting_id = make_meeting()
    response = client.post(f"/meetings/{meeting_id}/process")
    assert response.status_code == 404
    assert response.json()["detail"] == "No audio uploaded for this meeting."


def test_process_missing_meeting_is_404():
    assert client.post("/meetings/nope/process").status_code == 404
    assert client.get("/meetings/nope/status").status_code == 404


def test_process_runs_and_reports_ready():
    meeting_id = processed_meeting()
    status = client.get(f"/meetings/{meeting_id}/status").json()
    assert status["status"] == "READY"
    assert status["progress"] == 100
    assert client.get(f"/meetings/{meeting_id}").json()["status"] == "processed"


def test_status_before_processing_is_queued():
    meeting_id = make_meeting()
    assert client.get(f"/meetings/{meeting_id}/status").json()["status"] == "QUEUED"


def test_failure_is_reported_and_retry_recovers(monkeypatch):
    def broken(path, language=None):
        raise AudioPreprocessingError("Could not decode audio file (bad data).")

    monkeypatch.setattr(pipeline, "transcribe_audio", broken)
    meeting_id = make_meeting()
    upload(meeting_id)
    client.post(f"/meetings/{meeting_id}/process")

    status = client.get(f"/meetings/{meeting_id}/status").json()
    assert status["status"] == "FAILED"
    assert "Could not decode" in status["error"]

    monkeypatch.setattr(pipeline, "transcribe_audio", lambda path, language=None: FAKE_TRANSCRIPTION)
    assert client.post(f"/meetings/{meeting_id}/retry").status_code == 202
    assert client.get(f"/meetings/{meeting_id}/status").json()["status"] == "READY"


def test_no_speech_fails_with_clear_message(monkeypatch):
    monkeypatch.setattr(
        pipeline, "transcribe_audio", lambda path, language=None: {**FAKE_TRANSCRIPTION, "text": "  "}
    )
    meeting_id = make_meeting()
    upload(meeting_id)
    client.post(f"/meetings/{meeting_id}/process")
    status = client.get(f"/meetings/{meeting_id}/status").json()
    assert status["status"] == "FAILED"
    assert status["error"] == "No speech was detected in the audio."


def test_language_from_form_is_passed_to_transcription(monkeypatch):
    seen = {}

    def spy(path, language=None):
        seen["language"] = language
        return FAKE_TRANSCRIPTION

    monkeypatch.setattr(pipeline, "transcribe_audio", spy)
    meeting_id = make_meeting(language="hi")
    upload(meeting_id)
    client.post(f"/meetings/{meeting_id}/process")
    assert seen["language"] == "hi"


# ------------------------------------------------------------------ minutes
def test_minutes_not_ready_is_404():
    meeting_id = make_meeting()
    assert client.get(f"/meetings/{meeting_id}/minutes").status_code == 404


def test_minutes_have_the_shape_the_ui_expects():
    meeting_id = processed_meeting()
    minutes = client.get(f"/meetings/{meeting_id}/minutes").json()

    assert minutes["version"] == 1
    assert minutes["title"] == "Demo planning"
    assert minutes["datetime"] == "2026-11-02T10:00"
    assert minutes["agenda"] == "Demo plan"
    assert minutes["attendees"] == [{"name": "Ravi", "email": "ravi@example.com"}]
    assert minutes["topics"][0]["title"] == "Demo"
    assert minutes["decisions"][0]["statement"] == "Use a pre-recorded demo"

    first, second = minutes["actionItems"]
    assert first["owner"] == "Ravi"
    assert first["due"] == "2026-11-04"  # next Wednesday after Monday 2 Nov
    assert second["owner"] == "Unassigned"
    assert second["due"] == ""
    assert "before the review" in second["task"]  # unparseable deadline is kept as text
    assert all(item["id"] for item in minutes["actionItems"])


def test_basic_engine_output_is_flagged_for_review(monkeypatch):
    basic = {
        "engine": "basic",
        "summary": "x",
        "key_discussions": ["We met."],
        "decisions": ["We decided to ship."],
        "action_items": ["Sam will test it."],
        "transcript": "x",
    }
    monkeypatch.setattr(pipeline, "generate_minutes", lambda text, segments=None: basic)
    meeting_id = processed_meeting()
    minutes = client.get(f"/meetings/{meeting_id}/minutes").json()
    assert minutes["decisions"][0]["confidence"] < 0.6
    assert minutes["actionItems"][0]["confidence"] < 0.6
    assert minutes["actionItems"][0]["owner"] == "Unassigned"


def test_basic_engine_guesses_owner_and_deadline_from_attendees(monkeypatch):
    basic = {
        "engine": "basic",
        "summary": "x",
        "key_discussions": [],
        "decisions": [],
        "action_items": ["Ravi will finish the editor by Wednesday.", "Someone should book a room."],
        "transcript": "x",
    }
    monkeypatch.setattr(pipeline, "generate_minutes", lambda text, segments=None: basic)
    meeting_id = processed_meeting()  # attendee Ravi, meeting on Monday 2026-11-02
    first, second = client.get(f"/meetings/{meeting_id}/minutes").json()["actionItems"]
    assert first["owner"] == "Ravi"
    assert first["due"] == "2026-11-04"
    assert second["owner"] == "Unassigned"
    assert second["due"] == ""


def test_edits_are_saved_and_versioned():
    meeting_id = processed_meeting()
    minutes = client.get(f"/meetings/{meeting_id}/minutes").json()
    minutes["title"] = "Edited title"
    minutes["actionItems"][0]["status"] = "Done"

    saved = client.put(f"/meetings/{meeting_id}/minutes", json={"content": minutes})
    assert saved.status_code == 200
    assert saved.json() == {"version": 2}

    again = client.get(f"/meetings/{meeting_id}/minutes").json()
    assert again["version"] == 2
    assert again["title"] == "Edited title"
    assert again["actionItems"][0]["status"] == "Done"


def test_saving_stale_version_conflicts():
    meeting_id = processed_meeting()
    minutes = client.get(f"/meetings/{meeting_id}/minutes").json()
    assert client.put(f"/meetings/{meeting_id}/minutes", json={"content": minutes}).status_code == 200
    stale = client.put(f"/meetings/{meeting_id}/minutes", json={"content": minutes})
    assert stale.status_code == 409


def test_save_rejects_invalid_content():
    meeting_id = processed_meeting()
    minutes = client.get(f"/meetings/{meeting_id}/minutes").json()
    minutes["actionItems"][0]["status"] = "Maybe"
    assert client.put(f"/meetings/{meeting_id}/minutes", json={"content": minutes}).status_code == 422


# ------------------------------------------------------------------- export
@pytest.mark.parametrize(
    "fmt,magic",
    [("md", b"# Minutes of Meeting"), ("docx", b"PK"), ("pdf", b"%PDF")],
)
def test_export_formats(fmt, magic):
    meeting_id = processed_meeting()
    response = client.post(f"/meetings/{meeting_id}/export", json={"format": fmt})
    assert response.status_code == 200
    assert response.content.startswith(magic)
    assert f"minutes.{fmt}" in response.headers["content-disposition"]


def test_export_uses_unsaved_content_when_given():
    meeting_id = processed_meeting()
    minutes = client.get(f"/meetings/{meeting_id}/minutes").json()
    minutes["title"] = "Unsaved <title> & more"
    response = client.post(
        f"/meetings/{meeting_id}/export", json={"format": "md", "content": minutes}
    )
    assert "Unsaved <title> & more" in response.text


def test_export_pdf_survives_special_characters():
    meeting_id = processed_meeting()
    minutes = client.get(f"/meetings/{meeting_id}/minutes").json()
    minutes["topics"][0]["summary"] = "R&D <b>costs</b> > budget"
    response = client.post(
        f"/meetings/{meeting_id}/export", json={"format": "pdf", "content": minutes}
    )
    assert response.status_code == 200 and response.content.startswith(b"%PDF")


def test_export_invalid_format_rejected():
    meeting_id = processed_meeting()
    assert client.post(f"/meetings/{meeting_id}/export", json={"format": "exe"}).status_code == 422


# ------------------------------------------------------------ old endpoint
def test_sync_transcribe_maps_bad_audio_to_client_errors(monkeypatch):
    import app.main as main

    def broken(path, language=None):
        raise AudioPreprocessingError("Could not decode audio file (bad data).")

    monkeypatch.setattr(main, "transcribe_audio", broken)
    meeting_id = make_meeting()
    upload(meeting_id)
    response = client.post(f"/meetings/{meeting_id}/transcribe")
    assert response.status_code == 422
    assert "Could not decode" in response.json()["detail"]


# ------------------------------------------------------------ deadlines
@pytest.mark.parametrize(
    "text,expected",
    [
        ("Wednesday", "2026-11-04"),
        ("by Friday", "2026-11-06"),
        ("Monday", "2026-11-09"),  # same weekday means next week
        ("tomorrow", "2026-11-03"),
        ("today", "2026-11-02"),
        ("Nov 20", "2026-11-20"),
        ("2026-12-01", "2026-12-01"),
        ("before the review", ""),
        ("", ""),
        (None, ""),
    ],
)
def test_resolve_deadline(text, expected):
    assert pipeline.resolve_deadline(text, "2026-11-02T10:00") == expected


def test_resolve_deadline_without_meeting_date_uses_today():
    assert pipeline.resolve_deadline("tomorrow") == (dt.date.today() + dt.timedelta(days=1)).isoformat()
