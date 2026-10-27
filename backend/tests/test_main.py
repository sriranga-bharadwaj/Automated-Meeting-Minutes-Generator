
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db

TEST_DATABASE_URL = "sqlite://"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine,
)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_meeting():
    response = client.post(
        "/meetings",
        json={
            "title": "AMMG Sprint Planning",
            "description": "Discuss sprint tasks and responsibilities.",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "AMMG Sprint Planning"
    assert data["description"] == "Discuss sprint tasks and responsibilities."
    assert data["status"] == "created"
    assert "id" in data
    assert "created_at" in data


def test_list_meetings():
    client.post(
        "/meetings",
        json={"title": "Meeting One", "description": "First meeting"},
    )

    response = client.get("/meetings")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["title"] == "Meeting One"


def test_get_meeting():
    create_response = client.post(
        "/meetings",
        json={
            "title": "Meeting Details",
            "description": "Testing meeting retrieval",
        },
    )

    meeting_id = create_response.json()["id"]
    response = client.get(f"/meetings/{meeting_id}")

    assert response.status_code == 200
    assert response.json()["id"] == meeting_id
    assert response.json()["title"] == "Meeting Details"


def test_get_missing_meeting():
    response = client.get("/meetings/nonexistent-id")

    assert response.status_code == 404
    assert response.json()["detail"] == "Meeting not found."

    
def test_create_meeting_with_blank_title():
    response = client.post(
        "/meetings",
        json={
            "title": "   ",
            "description": "Testing blank title validation.",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Meeting title cannot be blank."



def test_create_meeting_with_missing_title():
    response = client.post(
        "/meetings",
        json={"description": "Meeting title was omitted."},
    )

    assert response.status_code == 422
    error = response.json()["detail"]
    assert any(
        item["loc"] == ["body", "title"]
        and item["type"] == "missing"
        for item in error
    )

    
from pathlib import Path

from app.main import AUDIO_UPLOAD_DIR, MAX_AUDIO_SIZE


def create_test_meeting():
    response = client.post(
        "/meetings",
        json={
            "title": "Audio Upload Test",
            "description": "Testing audio upload.",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_upload_audio_success():
    meeting_id = create_test_meeting()

    response = client.post(
        f"/meetings/{meeting_id}/audio",
        files={"file": ("test.wav", b"fake audio data", "audio/wav")},
    )

    assert response.status_code == 201
    assert response.json()["status"] == "uploaded"

    audio_path = AUDIO_UPLOAD_DIR / f"{response.json()['audio_id']}.wav"
    audio_path.unlink(missing_ok=True)


def test_upload_unsupported_audio_type():
    meeting_id = create_test_meeting()

    response = client.post(
        f"/meetings/{meeting_id}/audio",
        files={"file": ("test.txt", b"not audio", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported audio file type."


def test_upload_audio_for_missing_meeting():
    response = client.post(
        "/meetings/nonexistent-meeting/audio",
        files={"file": ("test.wav", b"fake audio data", "audio/wav")},
    )

    assert response.status_code == 404


def test_upload_audio_over_size_limit():
    meeting_id = create_test_meeting()

    response = client.post(
        f"/meetings/{meeting_id}/audio",
        files={
            "file": (
                "large.wav",
                b"x" * (MAX_AUDIO_SIZE + 1),
                "audio/wav",
            )
        },
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "Audio file exceeds the 25 MB limit."

    for path in AUDIO_UPLOAD_DIR.glob("*.wav"):
        # The endpoint removes the oversized partial upload.
        # Other test files should not be affected in normal test runs.
        if path.stat().st_size == 0:
            path.unlink(missing_ok=True)

