"""Security requirements: Argon2id, sessions and refresh tokens, rate limiting, audit log,
security headers, HTTPS redirect, sanitising, upload checks and encryption at rest."""
import wave

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import audit, auth, crypto, security
from app.audio_check import AudioCheckError, check_audio_file
from app.database import Base, get_db
from app.main import app
from app.models import AuditDB, MeetingDB, TranscriptDB


@pytest.fixture()
def env(monkeypatch):
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
    yield TestClient(app), Session
    security.limiter.reset()
    if previous is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = previous


def register(client, email="a@x.com", name="Ann", password="password123"):
    res = client.post("/auth/register", json={"name": name, "email": email, "password": password})
    assert res.status_code == 201, res.text
    return res.json()


def bearer(data):
    return {"Authorization": f"Bearer {data['token']}"}


# ------------------------------------------------------------------ SR-003 Argon2id
def test_new_passwords_use_argon2id(env):
    client, Session = env
    register(client)
    with Session() as db:
        stored = db.execute(text("select password_hash from users")).scalar()
    assert stored.startswith("$argon2id$")


def test_old_scrypt_hash_still_logs_in_and_is_upgraded(env):
    import hashlib, os
    client, Session = env
    register(client)
    salt = os.urandom(16)
    old = f"scrypt${salt.hex()}${hashlib.scrypt(b'password123', salt=salt, n=2**14, r=8, p=1, dklen=32).hex()}"
    with Session() as db:
        db.execute(text("update users set password_hash = :h"), {"h": old})
        db.commit()
    assert auth.verify_password("password123", old)
    assert client.post("/auth/login", json={"email": "a@x.com", "password": "password123"}).status_code == 200
    with Session() as db:
        assert db.execute(text("select password_hash from users")).scalar().startswith("$argon2id$")


# ------------------------------------------------------------------ SR-004 sessions
def test_access_token_lifetime_is_30_minutes():
    assert auth.TOKEN_LIFETIME_SECONDS == 30 * 60


def test_refresh_rotates_and_old_token_cannot_be_reused(env):
    client, _ = env
    first = register(client)
    second = client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert second.status_code == 200
    new = second.json()
    assert new["refresh_token"] != first["refresh_token"]
    assert client.get("/meetings", headers=bearer(new)).status_code == 200

    # Presenting the used refresh token again is treated as theft: every session ends.
    reuse = client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert reuse.status_code == 401
    assert client.get("/meetings", headers=bearer(new)).status_code == 401
    assert client.post("/auth/refresh", json={"refresh_token": new["refresh_token"]}).status_code == 401


def test_logout_invalidates_the_session(env):
    client, _ = env
    data = register(client)
    assert client.get("/meetings", headers=bearer(data)).status_code == 200
    out = client.post("/auth/logout", json={"refresh_token": data["refresh_token"]}, headers=bearer(data))
    assert out.status_code == 200
    assert client.get("/meetings", headers=bearer(data)).status_code == 401           # access token dead
    assert client.post("/auth/refresh", json={"refresh_token": data["refresh_token"]}).status_code == 401


def test_unknown_refresh_token_is_refused(env):
    client, _ = env
    assert client.post("/auth/refresh", json={"refresh_token": "nope"}).status_code == 401


# ------------------------------------------------------------------ SR-007 rate limits
def test_login_is_limited_to_10_per_minute(env, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    client, _ = env
    register(client)
    codes = [
        client.post("/auth/login", json={"email": "nobody@x.com", "password": "whatever1"}).status_code
        for _ in range(security.LOGIN_LIMIT_PER_MIN + 2)
    ]
    assert codes[: security.LOGIN_LIMIT_PER_MIN] == [401] * security.LOGIN_LIMIT_PER_MIN
    assert codes[-1] == 429


def test_api_is_limited_per_user_and_answers_429(env, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setattr(security, "USER_LIMIT_PER_MIN", 5)
    client, _ = env
    data = register(client)
    codes = [client.get("/meetings", headers=bearer(data)).status_code for _ in range(7)]
    assert codes[:5] == [200] * 5
    assert codes[5] == 429
    blocked = client.get("/meetings", headers=bearer(data))
    assert blocked.status_code == 429 and "Retry-After" in blocked.headers


def test_limiter_window_expires():
    limiter = security.RateLimiter()
    assert limiter.check("k", 2, now=0) == 0
    assert limiter.check("k", 2, now=1) == 0
    assert limiter.check("k", 2, now=2) > 0
    assert limiter.check("k", 2, now=61) == 0


# ------------------------------------------------------------------ SR-008 audit log
def test_events_are_written_to_a_hash_chained_audit_log(env):
    client, Session = env
    admin = register(client, "admin@x.com", "Admin")
    user = register(client, "u@x.com", "User")
    client.post("/auth/login", json={"email": "u@x.com", "password": "wrong-pass1"})
    client.put(f"/admin/users/{user['user']['id']}/role", json={"role": "admin"}, headers=bearer(admin))
    meeting = client.post("/meetings", json={"title": "x"}, headers=bearer(user)).json()["id"]
    client.delete(f"/meetings/{meeting}", headers=bearer(user))

    events = [e["event"] for e in client.get("/admin/audit", headers=bearer(admin)).json()]
    for expected in ("register", "login-failed", "role-change", "meeting-delete"):
        assert expected in events
    assert client.get("/admin/audit/verify", headers=bearer(admin)).json() == {"intact": True, "first_bad_id": None}


def test_tampering_with_the_audit_log_is_detected(env):
    client, Session = env
    admin = register(client, "admin@x.com", "Admin")
    register(client, "u@x.com", "User")
    with Session() as db:
        db.execute(text("update audit_log set detail = 'edited' where id = 1"))
        db.commit()
    result = client.get("/admin/audit/verify", headers=bearer(admin)).json()
    assert result == {"intact": False, "first_bad_id": 1}


def test_deleting_a_middle_audit_row_is_detected(env):
    client, Session = env
    admin = register(client, "admin@x.com", "Admin")
    register(client, "u@x.com", "User")
    register(client, "v@x.com", "Vee")
    with Session() as db:
        rows = db.query(AuditDB).order_by(AuditDB.id).all()
        assert len(rows) >= 3
        db.delete(rows[1])
        db.commit()
    assert client.get("/admin/audit/verify", headers=bearer(admin)).json()["intact"] is False


def test_old_audit_rows_are_purged_after_a_year(env):
    _, Session = env
    from datetime import datetime, timedelta
    with Session() as db:
        audit.log(db, "old-event")
        db.execute(text("update audit_log set ts = :t"), {"t": datetime.utcnow() - timedelta(days=400)})
        db.commit()
        audit.log(db, "new-event")
        assert audit.purge_old(db) == 1
        assert [r.event for r in db.query(AuditDB).all()] == ["new-event"]


def test_role_change_needs_admin_and_keeps_one_admin(env):
    client, _ = env
    admin = register(client, "admin@x.com", "Admin")
    user = register(client, "u@x.com", "User")
    uid = user["user"]["id"]
    assert client.put(f"/admin/users/{uid}/role", json={"role": "admin"}, headers=bearer(user)).status_code == 403
    only_admin = admin["user"]["id"]
    assert client.put(f"/admin/users/{only_admin}/role", json={"role": "user"}, headers=bearer(admin)).status_code == 409
    assert client.put(f"/admin/users/{uid}/role", json={"role": "bogus"}, headers=bearer(admin)).status_code == 400
    assert client.put(f"/admin/users/{uid}/role", json={"role": "admin"}, headers=bearer(admin)).json()["role"] == "admin"


# ------------------------------------------------------------------ SR-010 headers and sanitising
def test_security_headers_are_sent(env):
    client, _ = env
    res = client.get("/health")
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in res.headers["Content-Security-Policy"]
    assert res.headers["Referrer-Policy"] == "no-referrer"
    assert "Content-Security-Policy" not in client.get("/docs").headers      # docs page loads its own scripts
    assert client.get("/meetings").headers["X-Frame-Options"] == "DENY"       # also on the 401 answer


def test_html_in_text_is_removed_before_it_is_stored(env):
    client, _ = env
    data = register(client)
    res = client.post(
        "/meetings",
        json={"title": "<script>alert(1)</script>Budget<b>!</b>", "agenda": "<img src=x onerror=alert(1)>Plan",
              "attendees": [{"name": "<i>Ravi</i>", "email": "r@x.com"}]},
        headers=bearer(data),
    )
    assert res.json()["title"] == "alert(1)Budget!"
    assert "<" not in res.text


def test_sanitize_helpers():
    assert security.sanitize_text("a<b>c</b>\x00d") == "acd"
    assert security.sanitize_obj({"x": ["<p>1</p>", {"y": "<u>2</u>"}], "n": 3}) == {"x": ["1", {"y": "2"}], "n": 3}
    assert security.sanitize_text("fewer than 5 users") == "fewer than 5 users"


# ------------------------------------------------------------------ SR-001 HTTPS
def test_http_is_redirected_to_https_when_forced(env, monkeypatch):
    client, _ = env
    monkeypatch.setenv("FORCE_HTTPS", "true")
    res = client.get("/health", follow_redirects=False)
    assert res.status_code == 307 and res.headers["location"].startswith("https://")
    monkeypatch.setenv("FORCE_HTTPS", "false")
    assert client.get("/health").status_code == 200


def test_hsts_is_sent_over_https(env):
    client, _ = env
    secure = TestClient(app, base_url="https://testserver")
    assert "max-age" in secure.get("/health").headers["Strict-Transport-Security"]
    assert "Strict-Transport-Security" not in client.get("/health").headers


# ------------------------------------------------------------------ SR-006 upload checks
def write_wav(path):
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(b"\x00\x00" * 1600)


@pytest.fixture()
def checks_on(monkeypatch):
    monkeypatch.setenv("AUDIO_PREVALIDATE", "true")


def test_signature_must_match_the_extension(checks_on, tmp_path):
    wav = tmp_path / "a.wav"
    write_wav(wav)
    check_audio_file(str(wav), "audio/wav", ".wav")
    renamed = tmp_path / "a.mp3"
    renamed.write_bytes(wav.read_bytes())            # a real WAV pretending to be an MP3
    with pytest.raises(AudioCheckError):
        check_audio_file(str(renamed), "audio/mpeg", ".mp3")
    exe = tmp_path / "evil.wav"
    exe.write_bytes(b"MZ\x90\x00" + b"\x00" * 100)    # a Windows program named .wav
    with pytest.raises(AudioCheckError):
        check_audio_file(str(exe), "audio/wav", ".wav")


def test_wrong_content_type_is_refused(checks_on, tmp_path):
    wav = tmp_path / "a.wav"
    write_wav(wav)
    with pytest.raises(AudioCheckError):
        check_audio_file(str(wav), "text/html", ".wav")
    check_audio_file(str(wav), "application/octet-stream", ".wav")      # generic types are allowed


def test_virus_scan_is_used_when_available(checks_on, tmp_path, monkeypatch):
    from app import audio_check
    wav = tmp_path / "a.wav"
    write_wav(wav)

    class Result:
        returncode = 1

    monkeypatch.setattr(audio_check, "_scanner", lambda: "clamscan")
    monkeypatch.setattr(audio_check.subprocess, "run", lambda *a, **k: Result())
    with pytest.raises(AudioCheckError) as err:
        check_audio_file(str(wav), "audio/wav", ".wav")
    assert "virus" in str(err.value)
    monkeypatch.setattr(audio_check, "_scanner", lambda: None)
    check_audio_file(str(wav), "audio/wav", ".wav")                     # skipped without ClamAV
    assert audio_check.virus_scanner_available() is False


def test_uploaded_files_get_random_names_and_are_encrypted(env, monkeypatch, tmp_path):
    from app import api_v1, main
    monkeypatch.setenv("AUDIO_PREVALIDATE", "true")
    monkeypatch.setattr(main, "AUDIO_UPLOAD_DIR", tmp_path)
    client, _ = env
    data = register(client)
    meeting = client.post("/meetings", json={"title": "x"}, headers=bearer(data)).json()["id"]
    wav = tmp_path / "source.wav"
    write_wav(wav)
    res = client.post(f"/meetings/{meeting}/audio", files={"file": ("my voice.wav", wav.read_bytes(), "audio/wav")}, headers=bearer(data))
    assert res.status_code == 201
    stored = [p for p in tmp_path.iterdir() if p.name != "source.wav"]
    assert len(stored) == 1 and "my voice" not in stored[0].name
    assert crypto.is_encrypted_file(stored[0])
    bad = client.post(f"/meetings/{meeting}/audio", files={"file": ("x.wav", b"MZ not audio", "audio/wav")}, headers=bearer(data))
    assert bad.status_code == 400


# ------------------------------------------------------------------ SR-002 encryption at rest
def test_text_round_trips_and_plain_values_still_read():
    sealed = crypto.encrypt_text("secret transcript")
    assert sealed.startswith("enc1:") and "secret" not in sealed
    assert crypto.decrypt_text(sealed) == "secret transcript"
    assert crypto.decrypt_text("stored before encryption") == "stored before encryption"
    assert crypto.encrypt_text("same") != crypto.encrypt_text("same")      # fresh nonce each time


def test_transcripts_and_minutes_are_encrypted_in_the_database(env):
    client, Session = env
    from app import pipeline
    with Session() as db:
        meeting = MeetingDB(id="m1", title="t", description="", status="created")
        db.add(meeting)
        db.commit()
        from app.models import AudioDB
        audio = AudioDB(id="a1", meeting_id="m1", filename="a.wav", file_path="x", size_bytes=1)
        db.add(audio)
        pipeline.persist_result(
            db, meeting, audio,
            {"text": "Ravi will fix the login page", "segments": [{"start": 0, "end": 2, "text": "Ravi will fix the login page"}]},
            {"engine": "basic", "decisions": [], "action_items": [], "key_discussions": []},
        )
        db.commit()
        raw_text = db.execute(text("select text from transcripts")).scalar()
        raw_segments = db.execute(text("select segments_json from transcripts")).scalar()
        raw_minutes = db.execute(text("select content_json from minutes")).scalar()
        assert raw_text.startswith("enc1:") and raw_segments.startswith("enc1:") and raw_minutes.startswith("enc1:")
        assert "login" not in raw_text + raw_segments + raw_minutes
        assert db.query(TranscriptDB).first().text == "Ravi will fix the login page"       # read back decrypted


def test_audio_file_encryption_round_trip(tmp_path):
    original = tmp_path / "a.wav"
    write_wav(original)
    before = original.read_bytes()
    crypto.encrypt_file(original)
    assert crypto.is_encrypted_file(original) and original.read_bytes() != before
    with crypto.decrypted_copy(original) as plain:
        assert plain.read_bytes() == before
        assert plain.name == "a.wav"
    crypto.encrypt_file(original)                                                         # a second call changes nothing
    with crypto.decrypted_copy(original) as plain:
        assert plain.read_bytes() == before


def test_large_audio_spans_several_chunks(tmp_path, monkeypatch):
    monkeypatch.setattr(crypto, "CHUNK", 1000)
    path = tmp_path / "big.bin"
    data = bytes(range(256)) * 40
    path.write_bytes(data)
    crypto.encrypt_file(path)
    with crypto.decrypted_copy(path) as plain:
        assert plain.read_bytes() == data


def test_a_changed_encrypted_file_is_not_accepted(tmp_path):
    path = tmp_path / "a.wav"
    write_wav(path)
    crypto.encrypt_file(path)
    blob = bytearray(path.read_bytes())
    blob[-5] ^= 0xFF
    path.write_bytes(bytes(blob))
    with pytest.raises(Exception):
        with crypto.decrypted_copy(path):
            pass


def test_encryption_can_be_switched_off(monkeypatch, tmp_path):
    monkeypatch.setenv("ENCRYPT_AT_REST", "false")
    path = tmp_path / "a.wav"
    write_wav(path)
    crypto.encrypt_file(path)
    assert not crypto.is_encrypted_file(path)
