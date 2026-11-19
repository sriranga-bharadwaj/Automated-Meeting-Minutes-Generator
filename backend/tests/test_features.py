"""Transcript editing and playback, source links, version history, sharing, action tracker,
reminders, retention and the admin console (app/features.py)."""
import smtplib
import wave
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import crypto, features, mailer, pipeline, security, sources
from app.database import Base, get_db
from app.main import app
from app.models import AudioDB, MeetingDB

SEGMENTS = [
    {"start": 0.0, "end": 6.0, "text": "Good morning everyone, let's start the review."},
    {"start": 6.0, "end": 14.0, "text": "We decided to move the database to a faster server before the final demo."},
    {"start": 14.0, "end": 20.0, "text": "Karthik will arrange the new server by Tuesday."},
    {"start": 20.0, "end": 27.0, "text": "Asha will update the test document by Thursday."},
]
RAW_MINUTES = {
    "engine": "llm",
    "title": "Generated title",
    "summary": "Status and server plans.",
    "topics": [{"title": "Server", "summary": "Move the database to a faster server."}],
    "decision_details": [{"decision": "Move the database to a faster server before the final demo"}],
    "action_item_details": [
        {"task": "Arrange the new server", "owner": "Karthik", "deadline": "Tuesday"},
        {"task": "Update the test document", "owner": "Asha", "deadline": "Thursday"},
    ],
}


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
    yield TestClient(app), Session, tmp_path
    if previous is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = previous


def register(client, email, name):
    res = client.post("/auth/register", json={"name": name, "email": email, "password": "password123"})
    data = res.json()
    return {"Authorization": f"Bearer {data['token']}"}, data["user"]["id"]


def seed(Session, tmp_path, owner_id, title="Weekly", segments=SEGMENTS, raw=RAW_MINUTES, created=None):
    """A processed meeting with an encrypted recording, a transcript and minutes."""
    audio_path = tmp_path / f"{title}.wav"
    with wave.open(str(audio_path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(b"\x01\x00" * 3200)
    original = audio_path.read_bytes()
    crypto.encrypt_file(audio_path)
    with Session() as db:
        meeting = MeetingDB(
            id=f"m-{title}", title=title, description="", status="created", owner_id=owner_id,
            details_json='{"datetime": "2026-11-18T10:00", "agenda": "", "language": "en", "attendees": ['
                         '{"name": "Karthik", "email": "karthik@example.com"}, {"name": "Asha", "email": "asha@example.com"}]}',
        )
        db.add(meeting)
        db.commit()
        audio = AudioDB(id=f"a-{title}", meeting_id=meeting.id, filename="rec.wav", file_path=str(audio_path), size_bytes=len(original))
        db.add(audio)
        pipeline.persist_result(
            db, meeting, audio,
            {"text": " ".join(s["text"] for s in segments), "language": "en", "segments": segments}, dict(raw),
        )
        if created is not None:
            db.execute(text("update meetings set created_at = :c where id = :i"), {"c": created, "i": meeting.id})
        db.commit()
        return meeting.id, original


# ------------------------------------------------------------------ AMG-F-022 transcript
def test_transcript_can_be_read_edited_and_persists(env):
    client, Session, tmp = env
    hdr, uid = register(client, "a@x.com", "Admin")
    mid, _ = seed(Session, tmp, uid)
    got = client.get(f"/meetings/{mid}/transcript", headers=hdr).json()
    assert len(got["segments"]) == 4 and got["segments"][0]["speaker"] == ""

    got["segments"][1]["text"] = "We decided to use a recorded demo."
    got["segments"][1]["speaker"] = "Ravi"
    got["segments"][0]["text"] = "<b>Hello</b> everyone"
    assert client.put(f"/meetings/{mid}/transcript", json={"segments": got["segments"]}, headers=hdr).status_code == 200

    again = client.get(f"/meetings/{mid}/transcript", headers=hdr).json()          # "reload the page"
    assert again["segments"][1]["text"] == "We decided to use a recorded demo."
    assert again["segments"][1]["speaker"] == "Ravi"
    assert again["segments"][0]["text"] == "Hello everyone"                        # tags removed
    assert "recorded demo" in again["text"]


def test_transcript_edit_is_checked(env):
    client, Session, tmp = env
    hdr, uid = register(client, "a@x.com", "Admin")
    mid, _ = seed(Session, tmp, uid)
    bad = client.put(f"/meetings/{mid}/transcript", json={"segments": [{"start": -1, "end": 2, "text": "x"}]}, headers=hdr)
    assert bad.status_code == 422
    assert client.get("/meetings/nope/transcript", headers=hdr).status_code == 404


def test_other_users_cannot_read_or_edit_a_transcript(env):
    client, Session, tmp = env
    admin, _ = register(client, "admin@x.com", "Admin")
    alice, alice_id = register(client, "alice@x.com", "Alice")
    bob, _ = register(client, "bob@x.com", "Bob")
    mid, _ = seed(Session, tmp, alice_id)
    assert client.get(f"/meetings/{mid}/transcript", headers=alice).status_code == 200
    assert client.get(f"/meetings/{mid}/transcript", headers=bob).status_code == 403
    assert client.put(f"/meetings/{mid}/transcript", json={"segments": []}, headers=bob).status_code == 403
    assert client.get(f"/meetings/{mid}/audio/stream", headers=bob).status_code == 403
    assert client.get(f"/meetings/{mid}/audio/stream", headers=admin).status_code == 200


def test_recording_is_decrypted_for_playback(env):
    client, Session, tmp = env
    hdr, uid = register(client, "a@x.com", "Admin")
    mid, original = seed(Session, tmp, uid)
    res = client.get(f"/meetings/{mid}/audio/stream", headers=hdr)
    assert res.status_code == 200 and res.content == original
    assert res.headers["content-type"].startswith("audio/")
    assert client.get(f"/meetings/{mid}/audio/stream").status_code == 401


# ------------------------------------------------------------------ AMG-F-042 source links
def test_minutes_items_are_linked_to_the_recording(env):
    client, Session, tmp = env
    hdr, uid = register(client, "a@x.com", "Admin")
    mid, _ = seed(Session, tmp, uid)
    minutes = client.get(f"/meetings/{mid}/minutes", headers=hdr).json()
    decision = minutes["decisions"][0]
    assert decision["source"]["start"] == 6.0 and decision["source"]["end"] == 14.0
    owners = {a["task"]: a["source"] for a in minutes["actionItems"]}
    assert owners["Arrange the new server"]["start"] == 14.0
    assert owners["Update the test document"]["start"] == 20.0


def test_links_follow_transcript_edits_and_unmatched_items_get_none(env):
    client, Session, tmp = env
    hdr, uid = register(client, "a@x.com", "Admin")
    mid, _ = seed(Session, tmp, uid)
    segs = client.get(f"/meetings/{mid}/transcript", headers=hdr).json()["segments"]
    segs[1]["start"], segs[1]["end"] = 100.0, 110.0
    client.put(f"/meetings/{mid}/transcript", json={"segments": segs}, headers=hdr)
    minutes = client.get(f"/meetings/{mid}/minutes", headers=hdr).json()
    assert minutes["decisions"][0]["source"]["start"] == 100.0
    assert sources.best_segment("zebra quantum telescope", SEGMENTS) is None
    assert sources.attach({"topics": [], "decisions": [], "actionItems": []}, []) == {"topics": [], "decisions": [], "actionItems": []}


# ------------------------------------------------------------------ AMG-F-043 version history
def save(client, hdr, mid, mutate):
    minutes = client.get(f"/meetings/{mid}/minutes", headers=hdr).json()
    mutate(minutes)
    res = client.put(f"/meetings/{mid}/minutes", json={"content": minutes}, headers=hdr)
    assert res.status_code == 200, res.text
    return res.json()["version"]


def test_every_save_keeps_the_old_version_and_it_can_be_restored(env):
    client, Session, tmp = env
    hdr, uid = register(client, "a@x.com", "Admin")
    mid, _ = seed(Session, tmp, uid)
    assert save(client, hdr, mid, lambda m: m["topics"][0].update(title="Edited once")) == 2
    assert save(client, hdr, mid, lambda m: m["topics"][0].update(title="Edited twice")) == 3

    listing = client.get(f"/meetings/{mid}/minutes/versions", headers=hdr).json()
    assert [v["version"] for v in listing] == [3, 2, 1]
    assert listing[0]["current"] is True and listing[1]["saved_by"] == "a@x.com"
    assert client.get(f"/meetings/{mid}/minutes/versions/2", headers=hdr).json()["topics"][0]["title"] == "Edited once"
    assert client.get(f"/meetings/{mid}/minutes/versions/3", headers=hdr).json()["topics"][0]["title"] == "Edited twice"
    assert client.get(f"/meetings/{mid}/minutes/versions/99", headers=hdr).status_code == 404

    restored = client.post(f"/meetings/{mid}/minutes/versions/2/restore", headers=hdr)
    assert restored.json() == {"version": 4}
    now = client.get(f"/meetings/{mid}/minutes", headers=hdr).json()
    assert now["version"] == 4 and now["topics"][0]["title"] == "Edited once"
    assert len(client.get(f"/meetings/{mid}/minutes/versions", headers=hdr).json()) == 4      # nothing was lost


def test_versions_belong_to_the_meeting_owner(env):
    client, Session, tmp = env
    register(client, "admin@x.com", "Admin")
    alice, alice_id = register(client, "alice@x.com", "Alice")
    bob, _ = register(client, "bob@x.com", "Bob")
    mid, _ = seed(Session, tmp, alice_id)
    assert client.get(f"/meetings/{mid}/minutes/versions", headers=bob).status_code == 403
    assert client.post(f"/meetings/{mid}/minutes/versions/1/restore", headers=bob).status_code == 403


# ------------------------------------------------------------------ AMG-F-045 sharing
@pytest.fixture()
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(mailer, "send", lambda to, subject, body, attachment=None: sent.append((to, subject, body, attachment)))
    return sent


def test_minutes_can_be_shared_by_email_in_each_format(env, outbox):
    client, Session, tmp = env
    hdr, uid = register(client, "a@x.com", "Admin")
    mid, _ = seed(Session, tmp, uid)
    for fmt, ext in (("pdf", ".pdf"), ("docx", ".docx"), ("md", ".md")):
        res = client.post(f"/meetings/{mid}/share", json={"emails": ["boss@example.com", "team@example.com"], "format": fmt}, headers=hdr)
        assert res.status_code == 200 and res.json() == {"sent": 2}
        to, subject, _, attachment = outbox[-1]
        assert to == ["boss@example.com", "team@example.com"] and "Weekly" in subject
        assert attachment[2].endswith(ext) and len(attachment[0]) > 100
    events = [e["event"] for e in client.get("/admin/audit", headers=hdr).json()]
    assert events.count("share") == 3


def test_share_checks_addresses_format_and_access(env, outbox):
    client, Session, tmp = env
    register(client, "admin@x.com", "Admin")
    alice, alice_id = register(client, "alice@x.com", "Alice")
    bob, _ = register(client, "bob@x.com", "Bob")
    mid, _ = seed(Session, tmp, alice_id)
    assert client.post(f"/meetings/{mid}/share", json={"emails": ["not-an-email"]}, headers=alice).status_code == 400
    assert client.post(f"/meetings/{mid}/share", json={"emails": ["a@b.com"], "format": "exe"}, headers=alice).status_code == 400
    assert client.post(f"/meetings/{mid}/share", json={"emails": []}, headers=alice).status_code == 422
    assert client.post(f"/meetings/{mid}/share", json={"emails": ["a@b.com"]}, headers=bob).status_code == 403
    assert outbox == []


def test_share_reports_a_mail_server_problem(env, monkeypatch):
    client, Session, tmp = env
    hdr, uid = register(client, "a@x.com", "Admin")
    mid, _ = seed(Session, tmp, uid)
    monkeypatch.delenv("SMTP_HOST", raising=False)
    res = client.post(f"/meetings/{mid}/share", json={"emails": ["a@b.com"]}, headers=hdr)
    assert res.status_code == 502 and "SMTP_HOST" in res.json()["message"]


def test_mailer_talks_smtp(monkeypatch):
    log = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=0):
            log["server"] = (host, port)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            log["tls"] = True

        def login(self, user, password):
            log["login"] = (user, password)

        def send_message(self, message):
            log["to"], log["subject"] = message["To"], message["Subject"]
            log["attachments"] = [p.get_filename() for p in message.iter_attachments()]

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setenv("SMTP_HOST", "mail.example.com")
    monkeypatch.setenv("SMTP_USER", "me")
    monkeypatch.setenv("SMTP_PASSWORD", "pw")
    mailer.send(["a@b.com", "c@d.com"], "Hi", "body", (b"data", "application/pdf", "minutes.pdf"))
    assert log == {
        "server": ("mail.example.com", 587), "tls": True, "login": ("me", "pw"),
        "to": "a@b.com, c@d.com", "subject": "Hi", "attachments": ["minutes.pdf"],
    }

    class Broken(FakeSMTP):
        def __init__(self, *a, **k):
            raise ConnectionRefusedError("down")

    monkeypatch.setattr(smtplib, "SMTP", Broken)
    with pytest.raises(mailer.MailError):
        mailer.send(["a@b.com"], "Hi", "body")


# ------------------------------------------------------------------ AMG-F-050 action tracker
def test_action_tracker_lists_filters_and_marks_done(env):
    client, Session, tmp = env
    hdr, uid = register(client, "a@x.com", "Admin")
    seed(Session, tmp, uid, title="One")
    seed(Session, tmp, uid, title="Two")
    rows = client.get("/actions", headers=hdr).json()
    assert len(rows) == 4 and {r["meeting_title"] for r in rows} == {"One", "Two"}
    assert all(r["status"] == "Open" for r in rows)

    karthik = client.get("/actions", params={"owner": "karth"}, headers=hdr).json()
    assert len(karthik) == 2 and all(r["owner"] == "Karthik" for r in karthik)

    target = karthik[0]
    res = client.patch(f"/meetings/{target['meeting_id']}/actions/{target['id']}", json={"status": "Done"}, headers=hdr)
    assert res.status_code == 200 and res.json()["version"] == 2
    assert len(client.get("/actions", params={"status": "Open"}, headers=hdr).json()) == 3
    done = client.get("/actions", params={"status": "Done"}, headers=hdr).json()
    assert [d["id"] for d in done] == [target["id"]]
    # the change is a new version of the minutes, so history shows it
    assert len(client.get(f"/meetings/{target['meeting_id']}/minutes/versions", headers=hdr).json()) == 2


def test_overdue_items_are_flagged_and_sorted_first(env):
    client, Session, tmp = env
    hdr, uid = register(client, "a@x.com", "Admin")
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    later = (date.today() + timedelta(days=30)).isoformat()
    raw = {**RAW_MINUTES, "action_item_details": [
        {"task": "Late job", "owner": "Karthik", "deadline": yesterday},
        {"task": "Future job", "owner": "Asha", "deadline": later},
        {"task": "Undated job", "owner": "Asha"},
    ]}
    seed(Session, tmp, uid, raw=raw)
    rows = client.get("/actions", headers=hdr).json()
    assert [r["task"] for r in rows] == ["Late job", "Future job", "Undated job"]
    assert rows[0]["overdue"] is True and rows[1]["overdue"] is False
    assert [r["task"] for r in client.get("/actions", params={"overdue": "true"}, headers=hdr).json()] == ["Late job"]


def test_action_tracker_shows_only_your_meetings(env):
    client, Session, tmp = env
    admin, _ = register(client, "admin@x.com", "Admin")
    alice, alice_id = register(client, "alice@x.com", "Alice")
    bob, bob_id = register(client, "bob@x.com", "Bob")
    seed(Session, tmp, alice_id, title="Alice")
    seed(Session, tmp, bob_id, title="Bob")
    assert {r["meeting_title"] for r in client.get("/actions", headers=alice).json()} == {"Alice"}
    assert {r["meeting_title"] for r in client.get("/actions", headers=admin).json()} == {"Alice", "Bob"}
    mine = client.get("/actions", headers=alice).json()[0]
    assert client.patch(f"/meetings/{mine['meeting_id']}/actions/{mine['id']}", json={"status": "Done"}, headers=bob).status_code == 403
    assert client.patch(f"/meetings/{mine['meeting_id']}/actions/{mine['id']}", json={"status": "Maybe"}, headers=alice).status_code == 400
    assert client.patch(f"/meetings/{mine['meeting_id']}/actions/zzz", json={"status": "Done"}, headers=alice).status_code == 404


# ------------------------------------------------------------------ AMG-F-051 reminders
def test_reminders_go_to_owners_once(env):
    client, Session, tmp = env
    hdr, uid = register(client, "a@x.com", "Admin")
    today = date.today()
    raw = {**RAW_MINUTES, "action_item_details": [
        {"task": "Due tomorrow", "owner": "Karthik", "deadline": (today + timedelta(days=1)).isoformat()},
        {"task": "Overdue", "owner": "Asha", "deadline": (today - timedelta(days=3)).isoformat()},
        {"task": "Far away", "owner": "Asha", "deadline": (today + timedelta(days=20)).isoformat()},
        {"task": "Nobody known", "owner": "Zed", "deadline": (today + timedelta(days=1)).isoformat()},
        {"task": "No date", "owner": "Asha"},
    ]}
    seed(Session, tmp, uid, raw=raw)
    sent = []
    with Session() as db:
        first = features.run_reminders(db, today=today, send=lambda to, subject, body: sent.append((to, subject, body)))
        second = features.run_reminders(db, today=today, send=lambda to, subject, body: sent.append((to, subject, body)))
    assert first == {"sent": 2, "skipped": 1, "failed": 0}
    assert sorted(s[0][0] for s in sent) == ["asha@example.com", "karthik@example.com"]
    assert any("overdue" in s[2] for s in sent) and any("is due on" in s[2] for s in sent)
    assert second["sent"] == 0                                                      # not sent twice


def test_reminder_skips_done_items_and_counts_mail_failures(env):
    client, Session, tmp = env
    hdr, uid = register(client, "a@x.com", "Admin")
    raw = {**RAW_MINUTES, "action_item_details": [{"task": "Soon", "owner": "Karthik", "deadline": date.today().isoformat()}]}
    mid, _ = seed(Session, tmp, uid, raw=raw)

    def broken(to, subject, body):
        raise mailer.MailError("down")

    with Session() as db:
        assert features.run_reminders(db, send=broken) == {"sent": 0, "skipped": 0, "failed": 1}
    item = client.get("/actions", headers=hdr).json()[0]
    client.patch(f"/meetings/{mid}/actions/{item['id']}", json={"status": "Done"}, headers=hdr)
    with Session() as db:
        assert features.run_reminders(db, send=lambda *a: None) == {"sent": 0, "skipped": 0, "failed": 0}


def test_admin_can_trigger_reminders(env, monkeypatch, outbox):
    client, Session, tmp = env
    hdr, uid = register(client, "a@x.com", "Admin")
    user, _ = register(client, "u@x.com", "User")
    raw = {**RAW_MINUTES, "action_item_details": [{"task": "Soon", "owner": "Asha", "deadline": date.today().isoformat()}]}
    seed(Session, tmp, uid, raw=raw)
    monkeypatch.delenv("SMTP_HOST", raising=False)
    assert client.post("/admin/reminders/run", headers=hdr).status_code == 502
    monkeypatch.setenv("SMTP_HOST", "mail.example.com")
    assert client.post("/admin/reminders/run", headers=user).status_code == 403
    assert client.post("/admin/reminders/run", headers=hdr).json()["sent"] == 1


# ------------------------------------------------------------------ AMG-F-061 retention
def test_old_meetings_and_their_audio_are_purged(env):
    client, Session, tmp = env
    hdr, uid = register(client, "a@x.com", "Admin")
    old_id, _ = seed(Session, tmp, uid, title="Old", created=datetime.utcnow() - timedelta(days=100))
    new_id, _ = seed(Session, tmp, uid, title="New")
    old_audio = tmp / "Old.wav"
    assert old_audio.exists()
    res = client.post("/admin/retention/run", params={"days": 90}, headers=hdr)
    assert res.json() == {"removed": 1, "days": 90}
    assert not old_audio.exists() and (tmp / "New.wav").exists()
    ids = [m["id"] for m in client.get("/meetings", headers=hdr).json()]
    assert ids == [new_id]
    assert client.post("/admin/retention/run", headers=hdr).status_code == 400          # no number of days given
    assert "retention-purge" in [e["event"] for e in client.get("/admin/audit", headers=hdr).json()]


def test_retention_needs_admin(env):
    client, _, _ = env
    register(client, "admin@x.com", "Admin")
    user, _ = register(client, "u@x.com", "User")
    assert client.post("/admin/retention/run", params={"days": 1}, headers=user).status_code == 403


# ------------------------------------------------------------------ AMG-F-060 job monitoring
def test_admin_console_lists_jobs(env):
    client, Session, tmp = env
    admin, uid = register(client, "admin@x.com", "Admin")
    user, user_id = register(client, "u@x.com", "User")
    seed(Session, tmp, user_id, title="Mine")
    jobs = client.get("/admin/jobs", headers=admin).json()
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Mine" and jobs[0]["owner_email"] == "u@x.com"
    assert jobs[0]["status"] == "READY" and jobs[0]["audio_file"] == "rec.wav"
    assert client.get("/admin/jobs", headers=user).status_code == 403
    assert client.get("/admin/audit", headers=user).status_code == 403


def test_background_loop_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("BACKGROUND_TASKS", "false")
    assert features.start_scheduler() is None


def test_same_routes_exist_under_api_v1(env):
    client, Session, tmp = env
    hdr, uid = register(client, "a@x.com", "Admin")
    mid, _ = seed(Session, tmp, uid)
    assert client.get(f"/api/v1/meetings/{mid}/transcript", headers=hdr).status_code == 200
    assert client.get("/api/v1/actions", headers=hdr).status_code == 200
