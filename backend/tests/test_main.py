
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
