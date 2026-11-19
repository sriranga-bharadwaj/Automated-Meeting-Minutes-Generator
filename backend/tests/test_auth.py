"""Login, roles, ownership and lockout (app/auth.py)."""
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import auth
from app.database import Base, get_db
from app.main import app


@pytest.fixture()
def client(monkeypatch):
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
    yield TestClient(app)
    if previous is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = previous


def register(client, email, name="Person", password="password123"):
    return client.post("/auth/register", json={"name": name, "email": email, "password": password})


def headers(response):
    return {"Authorization": f"Bearer {response.json()['token']}"}


def make_meeting(client, hdrs, title="Weekly"):
    res = client.post("/meetings", json={"title": title}, headers=hdrs)
    assert res.status_code == 201, res.text
    return res.json()["id"]


def test_first_account_is_admin_and_later_ones_are_organizers(client):
    first = register(client, "admin@example.com", "Admin")
    second = register(client, "user@example.com", "User")
    assert first.status_code == 201 and first.json()["user"]["role"] == "admin"
    assert second.json()["user"]["role"] == "organizer"


def test_register_rejects_bad_input_and_duplicates(client):
    assert register(client, "not-an-email").status_code == 400
    assert client.post("/auth/register", json={"name": "A", "email": "a@x.com", "password": "short"}).status_code == 422
    assert register(client, "a@x.com").status_code == 201
    assert register(client, "A@X.com").status_code == 409   # emails are not case sensitive


def test_login_works_and_wrong_password_is_refused(client):
    register(client, "a@x.com")
    ok = client.post("/auth/login", json={"email": "a@x.com", "password": "password123"})
    assert ok.status_code == 200 and ok.json()["token"]
    bad = client.post("/auth/login", json={"email": "a@x.com", "password": "nope-nope"})
    assert bad.status_code == 401
    unknown = client.post("/auth/login", json={"email": "who@x.com", "password": "password123"})
    assert unknown.status_code == 401 and unknown.json()["message"] == bad.json()["message"]


def test_account_locks_after_five_wrong_passwords(client):
    register(client, "a@x.com")
    for _ in range(auth.MAX_FAILED_ATTEMPTS):
        assert client.post("/auth/login", json={"email": "a@x.com", "password": "wrong-pass"}).status_code == 401
    locked = client.post("/auth/login", json={"email": "a@x.com", "password": "password123"})
    assert locked.status_code == 429
    assert "Try again" in locked.json()["message"]


def test_meeting_routes_need_a_token(client):
    assert client.get("/meetings").status_code == 401
    assert client.post("/meetings", json={"title": "x"}).status_code == 401
    assert client.get("/meetings", headers={"Authorization": "Bearer garbage"}).status_code == 401
    assert client.get("/health").status_code == 200   # public


def test_tampered_and_expired_tokens_are_refused(client, monkeypatch):
    res = register(client, "a@x.com")
    token = res.json()["token"]
    head, payload, sig = token.split(".")
    forged = ".".join([head, payload, sig[:-2] + ("AA" if not sig.endswith("AA") else "BB")])
    assert client.get("/meetings", headers={"Authorization": f"Bearer {forged}"}).status_code == 401

    monkeypatch.setattr(auth, "TOKEN_LIFETIME_SECONDS", -10)
    expired = register(client, "b@x.com").json()["token"]
    assert client.get("/meetings", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_user_cannot_open_another_users_meeting(client):
    admin = register(client, "admin@example.com", "Admin")
    alice = register(client, "alice@example.com", "Alice")
    bob = register(client, "bob@example.com", "Bob")
    meeting_id = make_meeting(client, headers(alice))

    assert client.get(f"/meetings/{meeting_id}", headers=headers(alice)).status_code == 200
    for path in (f"/meetings/{meeting_id}", f"/meetings/{meeting_id}/status", f"/meetings/{meeting_id}/minutes"):
        assert client.get(path, headers=headers(bob)).status_code == 403
    assert client.delete(f"/meetings/{meeting_id}", headers=headers(bob)).status_code == 403
    assert client.get(f"/meetings/{meeting_id}", headers=headers(admin)).status_code == 200


def test_meeting_list_is_filtered_by_role(client):
    admin = register(client, "admin@example.com", "Admin")
    alice = register(client, "alice@example.com", "Alice")
    bob = register(client, "bob@example.com", "Bob")
    make_meeting(client, headers(alice), "Alice meeting")
    make_meeting(client, headers(bob), "Bob meeting")

    alice_titles = [m["title"] for m in client.get("/meetings", headers=headers(alice)).json()]
    assert alice_titles == ["Alice meeting"]
    admin_list = client.get("/meetings", headers=headers(admin)).json()
    assert sorted(m["title"] for m in admin_list) == ["Alice meeting", "Bob meeting"]
    assert {m["owner_email"] for m in admin_list} == {"alice@example.com", "bob@example.com"}


def test_owner_and_admin_can_delete_a_meeting(client):
    admin = register(client, "admin@example.com", "Admin")
    alice = register(client, "alice@example.com", "Alice")
    mine = make_meeting(client, headers(alice))
    theirs = make_meeting(client, headers(alice), "Second")

    assert client.delete(f"/meetings/{mine}", headers=headers(alice)).status_code == 204
    assert client.get(f"/meetings/{mine}", headers=headers(alice)).status_code == 404
    assert client.delete(f"/meetings/{theirs}", headers=headers(admin)).status_code == 204


def test_only_admin_can_list_users(client):
    admin = register(client, "admin@example.com", "Admin")
    alice = register(client, "alice@example.com", "Alice")
    assert client.get("/admin/users", headers=headers(alice)).status_code == 403
    users = client.get("/admin/users", headers=headers(admin))
    assert users.status_code == 200 and len(users.json()) == 2
    assert "password_hash" not in users.text


def test_me_returns_the_signed_in_user(client):
    res = register(client, "a@x.com", "Ann")
    me = client.get("/auth/me", headers=headers(res))
    assert me.status_code == 200 and me.json()["name"] == "Ann"
    assert client.get("/auth/me").status_code == 401


def test_password_hash_is_salted_and_checked():
    one, two = auth.hash_password("secret-pass"), auth.hash_password("secret-pass")
    assert one != two
    assert auth.verify_password("secret-pass", one) and not auth.verify_password("other", one)
    assert not auth.verify_password("secret-pass", "garbage")


def test_checks_can_be_switched_off(client, monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "false")
    assert client.get("/meetings").status_code == 200
