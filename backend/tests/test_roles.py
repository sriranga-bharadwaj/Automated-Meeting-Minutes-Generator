"""AMG-F-002: roles Admin, Organizer, Participant; a person opens only meetings they own or
were invited to (their email is in the attendee list). Acceptance: another person's meeting
gives HTTP 403 (TC-Auth-02)."""
import wave

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import crypto, pipeline, security
from app.database import Base, get_db
from app.main import app
from app.models import AudioDB, MeetingDB

RAW = {
    "engine": "llm", "title": "x", "summary": "s", "topics": [{"title": "Server", "summary": "Move the database."}],
    "decision_details": [{"decision": "Move the database to a faster server"}],
    "action_item_details": [{"task": "Arrange the new server", "owner": "Priya", "deadline": "Tuesday"}],
}
SEGMENTS = [{"start": 0.0, "end": 5.0, "text": "We decided to move the database to a faster server."}]


@pytest.fixture()
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override
    security.limiter.reset()
    client = TestClient(app)
    admin = register(client, "admin@x.com", "Admin")           # the first account is the admin
    yield client, Session, tmp_path, admin
    if previous is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = previous


def register(client, email, name="Person"):
    data = client.post("/auth/register", json={"name": name, "email": email, "password": "password123"}).json()
    return {"hdr": {"Authorization": f"Bearer {data['token']}"}, "id": data["user"]["id"], "role": data["user"]["role"], "email": email}


def make_participant(client, admin, email, name="Pat"):
    person = register(client, email, name)
    res = client.put(f"/admin/users/{person['id']}/role", json={"role": "participant"}, headers=admin["hdr"])
    assert res.status_code == 200 and res.json()["role"] == "participant"
    return {**person, "role": "participant"}


def seed(Session, tmp_path, owner_id, attendees, title="Weekly"):
    audio_path = tmp_path / f"{title}.wav"
    with wave.open(str(audio_path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(b"\x01\x00" * 800)
    crypto.encrypt_file(audio_path)
    import json
    with Session() as db:
        meeting = MeetingDB(
            id=f"m-{title}", title=title, description="", status="created", owner_id=owner_id,
            details_json=json.dumps({"datetime": "2026-11-18T10:00", "agenda": "", "language": "en", "attendees": attendees}),
        )
        db.add(meeting)
        db.commit()
        audio = AudioDB(id=f"a-{title}", meeting_id=meeting.id, filename="r.wav", file_path=str(audio_path), size_bytes=10)
        db.add(audio)
        pipeline.persist_result(db, meeting, audio, {"text": SEGMENTS[0]["text"], "language": "en", "segments": SEGMENTS}, dict(RAW))
        db.commit()
        return meeting.id


READ_PATHS = ["", "/status", "/minutes", "/transcript", "/audio/stream", "/minutes/versions", "/minutes/with-sources"]


def test_there_are_three_roles(env):
    client, _, _, admin = env
    organizer = register(client, "org@x.com")
    assert admin["role"] == "admin" and organizer["role"] == "organizer"
    pat = make_participant(client, admin, "pat@x.com")
    assert pat["role"] == "participant"
    assert client.put(f"/admin/users/{pat['id']}/role", json={"role": "manager"}, headers=admin["hdr"]).status_code == 400


def test_uninvited_person_gets_403_on_every_route(env):
    client, Session, tmp, admin = env
    owner = register(client, "owner@x.com")
    stranger = register(client, "stranger@x.com")
    pat = make_participant(client, admin, "pat@x.com")
    mid = seed(Session, tmp, owner["id"], [{"name": "Priya", "email": "priya@x.com"}])
    for person in (stranger, pat):
        for path in READ_PATHS:
            assert client.get(f"/meetings/{mid}{path}", headers=person["hdr"]).status_code == 403, path
        assert client.delete(f"/meetings/{mid}", headers=person["hdr"]).status_code == 403
        assert client.post(f"/meetings/{mid}/export", json={"format": "md"}, headers=person["hdr"]).status_code == 403


def test_invited_organizer_and_participant_can_read_the_meeting(env):
    client, Session, tmp, admin = env
    owner = register(client, "owner@x.com")
    organizer = register(client, "Priya@X.com", "Priya")             # email case does not matter
    pat = make_participant(client, admin, "pat@x.com")
    mid = seed(Session, tmp, owner["id"], [{"name": "Priya", "email": "priya@x.com"}, {"name": "Pat", "email": "pat@x.com"}])
    for person in (organizer, pat):
        for path in READ_PATHS:
            assert client.get(f"/meetings/{mid}{path}", headers=person["hdr"]).status_code == 200, path
        exported = client.post(f"/meetings/{mid}/export", json={"format": "md"}, headers=person["hdr"])
        assert exported.status_code == 200 and b"Minutes" in exported.content


def test_invited_people_cannot_change_share_or_delete(env, monkeypatch):
    client, Session, tmp, admin = env
    owner = register(client, "owner@x.com")
    guest = register(client, "guest@x.com", "Guest")
    mid = seed(Session, tmp, owner["id"], [{"name": "Guest", "email": "guest@x.com"}])
    minutes = client.get(f"/meetings/{mid}/minutes", headers=guest["hdr"]).json()
    item = minutes["actionItems"][0]["id"]
    attempts = [
        client.put(f"/meetings/{mid}/minutes", json={"content": minutes}, headers=guest["hdr"]),
        client.put(f"/meetings/{mid}/transcript", json={"segments": []}, headers=guest["hdr"]),
        client.post(f"/meetings/{mid}/share", json={"emails": ["a@b.com"]}, headers=guest["hdr"]),
        client.post(f"/meetings/{mid}/minutes/versions/1/restore", headers=guest["hdr"]),
        client.patch(f"/meetings/{mid}/actions/{item}", json={"status": "Done"}, headers=guest["hdr"]),
        client.post(f"/meetings/{mid}/process", headers=guest["hdr"]),
        client.post(f"/meetings/{mid}/retry", headers=guest["hdr"]),
        client.delete(f"/meetings/{mid}", headers=guest["hdr"]),
    ]
    assert [a.status_code for a in attempts] == [403] * len(attempts)
    assert all("only view" in a.json()["message"] for a in attempts)
    # nothing changed
    assert client.get(f"/meetings/{mid}/minutes", headers=owner["hdr"]).json()["version"] == 1


def test_the_owner_keeps_full_access(env, monkeypatch):
    client, Session, tmp, admin = env
    owner = register(client, "owner@x.com")
    mid = seed(Session, tmp, owner["id"], [])
    minutes = client.get(f"/meetings/{mid}/minutes", headers=owner["hdr"]).json()
    assert client.put(f"/meetings/{mid}/minutes", json={"content": minutes}, headers=owner["hdr"]).status_code == 200
    assert client.put(f"/meetings/{mid}/transcript", json={"segments": []}, headers=owner["hdr"]).status_code == 200
    assert client.delete(f"/meetings/{mid}", headers=owner["hdr"]).status_code == 204


def test_participants_cannot_create_meetings_but_organizers_can(env):
    client, _, _, admin = env
    organizer = register(client, "org@x.com")
    pat = make_participant(client, admin, "pat@x.com")
    for url in ("/meetings", "/api/v1/meetings"):
        assert client.post(url, json={"title": "New"}, headers=pat["hdr"]).status_code == 403
        assert client.post(url, json={"title": "New"}, headers=organizer["hdr"]).status_code == 201
    assert "cannot create" in client.post("/meetings", json={"title": "x"}, headers=pat["hdr"]).json()["message"]
    assert client.post("/meetings", json={"title": "Admin's"}, headers=admin["hdr"]).status_code == 201


def test_meeting_list_has_owned_and_invited_meetings(env):
    client, Session, tmp, admin = env
    org = register(client, "org@x.com", "Org")
    other = register(client, "other@x.com", "Other")
    pat = make_participant(client, admin, "pat@x.com")
    seed(Session, tmp, org["id"], [{"name": "Pat", "email": "pat@x.com"}], title="Shared")
    seed(Session, tmp, org["id"], [], title="Private")
    seed(Session, tmp, other["id"], [{"name": "Org", "email": "org@x.com"}], title="Invites org")

    mine = {m["title"]: m for m in client.get("/meetings", headers=org["hdr"]).json()}
    assert set(mine) == {"Shared", "Private", "Invites org"}
    assert mine["Shared"]["owned"] is True and mine["Invites org"]["owned"] is False
    assert mine["Invites org"]["owner_email"] == "other@x.com"

    theirs = client.get("/meetings", headers=pat["hdr"]).json()
    assert [(m["title"], m["owned"]) for m in theirs] == [("Shared", False)]
    assert len(client.get("/meetings", headers=admin["hdr"]).json()) == 3


def test_attendees_added_through_the_v1_route_count_as_invited(env):
    client, _, _, admin = env
    owner = register(client, "owner@x.com")
    guest = register(client, "guest@x.com", "Guest")
    body = {"title": "V1 meeting", "attendees": [{"name": "Guest", "email": "guest@x.com"}]}
    mid = client.post("/api/v1/meetings", json=body, headers=owner["hdr"]).json()["meetingId"]
    assert client.get(f"/api/v1/meetings/{mid}/status", headers=guest["hdr"]).status_code == 200
    assert client.post(f"/api/v1/meetings/{mid}/retry", headers=guest["hdr"]).status_code == 403
    assert [m["title"] for m in client.get("/meetings", headers=guest["hdr"]).json()] == ["V1 meeting"]


def test_action_tracker_shows_invited_items_as_read_only(env):
    client, Session, tmp, admin = env
    org = register(client, "org@x.com")
    guest = register(client, "guest@x.com", "Guest")
    seed(Session, tmp, org["id"], [{"name": "Guest", "email": "guest@x.com"}], title="Shared")
    seed(Session, tmp, guest["id"], [], title="Mine")
    rows = client.get("/actions", headers=guest["hdr"]).json()
    by_meeting = {r["meeting_title"]: r for r in rows}
    assert by_meeting["Shared"]["can_edit"] is False and by_meeting["Mine"]["can_edit"] is True
    shared = by_meeting["Shared"]
    assert client.patch(f"/meetings/{shared['meeting_id']}/actions/{shared['id']}", json={"status": "Done"}, headers=guest["hdr"]).status_code == 403
    mine = by_meeting["Mine"]
    assert client.patch(f"/meetings/{mine['meeting_id']}/actions/{mine['id']}", json={"status": "Done"}, headers=guest["hdr"]).status_code == 200


def test_admin_can_open_everything(env):
    client, Session, tmp, admin = env
    org = register(client, "org@x.com")
    mid = seed(Session, tmp, org["id"], [])
    for path in READ_PATHS:
        assert client.get(f"/meetings/{mid}{path}", headers=admin["hdr"]).status_code == 200, path


def test_only_admins_can_change_roles(env):
    client, _, _, admin = env
    org = register(client, "org@x.com")
    pat = make_participant(client, admin, "pat@x.com")
    for person in (org, pat):
        assert client.put(f"/admin/users/{org['id']}/role", json={"role": "admin"}, headers=person["hdr"]).status_code == 403


def test_old_user_role_is_renamed_organizer_by_the_schema_update(tmp_path, monkeypatch):
    from app import database
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for uid, role in (("1", "user"), ("2", "admin"), ("3", "participant")):
            conn.exec_driver_sql(
                "INSERT INTO users (id, email, name, password_hash, role, failed_attempts, created_at) "
                f"VALUES ('{uid}', '{uid}@x.com', 'N', 'h', '{role}', 0, CURRENT_TIMESTAMP)"
            )
    monkeypatch.setattr(database, "engine", engine)
    database.ensure_schema()
    with engine.begin() as conn:
        roles = dict(conn.exec_driver_sql("SELECT id, role FROM users").fetchall())
    assert roles == {"1": "organizer", "2": "admin", "3": "participant"}
