"""Tests for the pipeline background processing and minutes shaping utilities."""
import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import database, pipeline
from app.database import Base
from app.models import AudioDB, MeetingDB, MinutesDB, TranscriptDB

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
def setup_db():
    Base.metadata.create_all(bind=engine)
    pipeline._JOBS.clear()
    yield
    Base.metadata.drop_all(bind=engine)


def test_set_and_get_job():
    pipeline.set_job("m1", "TRANSCRIBING", 25, "Running Whisper")
    job = pipeline.get_job("m1")
    assert job is not None
    assert job["status"] == "TRANSCRIBING"
    assert job["progress"] == 25
    assert job["stage"] == "Running Whisper"
    assert pipeline.is_running("m1") is True


def test_job_not_running_when_ready_or_failed():
    pipeline.set_job("m1", "READY", 100, "Done")
    assert pipeline.is_running("m1") is False

    pipeline.set_job("m2", "FAILED", 0, "Error", error="Audio decode failed")
    assert pipeline.is_running("m2") is False


def test_status_for_with_active_job():
    meeting = MeetingDB(id="m1", title="Test", status="created")
    pipeline.set_job("m1", "ANALYSING", 50, "Generating minutes")
    status = pipeline.status_for(meeting)
    assert status["status"] == "ANALYSING"
    assert status["progress"] == 50


def test_status_for_fallback_to_database():
    db = Session()
    meeting = MeetingDB(id="m1", title="Test", status="created")
    db.add(meeting)
    db.commit()

    # Before any upload
    status = pipeline.status_for(meeting)
    assert status["status"] == "QUEUED"

    # With meeting marked processed in DB
    meeting.status = "processed"
    db.commit()

    status_ready = pipeline.status_for(meeting)
    assert status_ready["status"] == "READY"
    assert status_ready["progress"] == 100
    db.close()


def test_persist_result():
    db = Session()
    meeting = MeetingDB(id="m1", title="Test", status="created")
    audio = AudioDB(id="a1", meeting_id="m1", filename="audio.wav", file_path="audio.wav", size_bytes=100)
    db.add(meeting)
    db.add(audio)
    db.commit()

    transcript_rec, minutes_rec = pipeline.persist_result(
        db, meeting, audio, FAKE_TRANSCRIPTION, LLM_MINUTES
    )
    assert transcript_rec.id is not None
    assert minutes_rec.id is not None
    assert meeting.status == "processed"
    db.close()


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


def test_guess_owner_matching():
    attendees = [{"name": "Ravi Kumar"}, {"name": "Priya Sharma"}]
    assert pipeline.guess_owner("Ravi will finish the report.", attendees) == "Ravi Kumar"
    assert pipeline.guess_owner("Priya is handling this.", attendees) == "Priya Sharma"
    assert pipeline.guess_owner("Nobody mentioned.", attendees) is None
