"""Login, roles, sessions and per-user access to meetings.

- Passwords: salted Argon2id hashes (AMG-SR-003). Older scrypt hashes still work and are
  upgraded to Argon2id at the next login.
- Access token: signed HS256 JWT that expires after 30 minutes. Refresh token: random value
  kept only as a hash in the ``sessions`` table; it rotates on every use, and logout (or a
  reused old refresh token) revokes the session, which also kills its access tokens (AMG-SR-004).
- Roles: "user" sees and changes only their own meetings; "admin" sees all meetings, can
  delete any meeting, list users, change roles and see jobs and the audit log. The first
  account registered becomes admin.
- Five wrong passwords lock an account for 15 minutes (AMG-F-003); login is also limited
  to 10 attempts per minute per address (AMG-SR-007).
- Login, logout, role changes and failures go to the audit log (AMG-SR-008).
- AUTH_REQUIRED=false switches the checks off (used by the older tests and for demos).
  AMMG_SECRET_KEY fixes the token signing key; otherwise one is created in .ammg_secret.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

from app import audit, security
from app.database import get_db
from app.models import (
    AudioDB, MeetingDB, MeetingMetaDB, MinutesDB, MinutesVersionDB, ReminderSentDB,
    SessionDB, TranscriptDB, UserDB,
)

TOKEN_LIFETIME_SECONDS = 30 * 60
REFRESH_LIFETIME_DAYS = 7
MAX_FAILED_ATTEMPTS = 5
LOCK_MINUTES = 15
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_hasher = PasswordHasher()   # Argon2id with the library's recommended cost


def auth_required() -> bool:
    return os.getenv("AUTH_REQUIRED", "true").strip().lower() not in {"0", "false", "no", "off"}


# ---------------------------------------------------------------- passwords
def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, stored: str) -> bool:
    if stored.startswith("$argon2"):
        try:
            return _hasher.verify(stored, password)
        except (VerificationError, InvalidHashError):
            return False
    try:  # hashes made before Argon2id was introduced
        _, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1, dklen=32
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


# ---------------------------------------------------------------- tokens
def _secret() -> bytes:
    env = os.getenv("AMMG_SECRET_KEY")
    if env:
        return env.encode()
    path = Path(".ammg_secret")
    if path.exists():
        return path.read_text().strip().encode()
    key = secrets.token_hex(32)
    path.write_text(key)
    return key.encode()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def make_token(user: UserDB, session_id: str) -> str:
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64(
        json.dumps(
            {
                "sub": user.id,
                "role": user.role,
                "sid": session_id,
                "exp": int(time.time()) + TOKEN_LIFETIME_SECONDS,
            }
        ).encode()
    )
    signature = _b64(hmac.new(_secret(), f"{header}.{payload}".encode(), hashlib.sha256).digest())
    return f"{header}.{payload}.{signature}"


def read_token(token: str) -> Optional[dict]:
    """The token's claims, or None when it is malformed, forged or expired."""
    try:
        header, payload, signature = token.split(".")
        expected = _b64(hmac.new(_secret(), f"{header}.{payload}".encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return None
        claims = json.loads(_unb64(payload))
        if int(claims.get("exp", 0)) < time.time():
            return None
        return claims
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def _hash_refresh(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


def issue(db: Session, user: UserDB) -> dict:
    """Start a session and return {token, refresh_token, user}."""
    refresh = secrets.token_urlsafe(48)
    session = SessionDB(
        id=str(uuid4()),
        user_id=user.id,
        refresh_hash=_hash_refresh(refresh),
        expires_at=_now() + timedelta(days=REFRESH_LIFETIME_DAYS),
    )
    db.add(session)
    db.commit()
    return {"token": make_token(user, session.id), "refresh_token": refresh, "user": _user_out(user)}


# ---------------------------------------------------------------- request checks
PUBLIC_PATHS = {"/", "/health", "/docs", "/redoc", "/openapi.json"}
MEETING_PATH = re.compile(r"^(?:/api/v1)?/(?:meetings|minutes)/([^/]+)")
LOGIN_PATH = re.compile(r"^(?:/api/v1)?/auth/login$")


def _is_public(path: str) -> bool:
    return (
        path in PUBLIC_PATHS
        or path.startswith("/auth/")
        or path.startswith("/api/v1/auth/")
        or path.startswith("/docs/")
    )


def _deny(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"code": code, "message": message, "detail": message})


class AuthMiddleware(BaseHTTPMiddleware):
    """Rate limits, checks the token and session, and checks the owner of per-meeting requests."""

    async def dispatch(self, request: Request, call_next):
        request.state.user = None
        path = request.url.path
        if request.method == "OPTIONS" or not auth_required():
            return await call_next(request)

        if request.method == "POST" and LOGIN_PATH.match(path) and security.rate_limit_enabled():
            wait = security.limiter.check(f"login:{security.client_ip(request)}", security.LOGIN_LIMIT_PER_MIN)
            if wait:
                return security.too_many(wait)
        if _is_public(path):
            return await call_next(request)

        header = request.headers.get("authorization", "")
        claims = read_token(header[7:]) if header.lower().startswith("bearer ") else None
        if claims is None:
            return _deny(401, "UNAUTHENTICATED", "Your session has expired. Please log in again.")

        # Same session source as the routes use (tests replace get_db with their own database).
        session_source = request.app.dependency_overrides.get(get_db, get_db)()
        db = next(session_source)
        try:
            user = db.query(UserDB).filter(UserDB.id == claims["sub"]).first()
            session = db.query(SessionDB).filter(SessionDB.id == claims.get("sid", "")).first()
            if user is None or session is None or session.revoked:
                return _deny(401, "UNAUTHENTICATED", "Your session has expired. Please log in again.")
            request.state.user = {"id": user.id, "role": user.role, "email": user.email, "name": user.name}

            if security.rate_limit_enabled():
                wait = security.limiter.check(f"user:{user.id}", security.USER_LIMIT_PER_MIN)
                if wait:
                    return security.too_many(wait)

            if path.startswith(("/admin/", "/api/v1/admin/")) and user.role != "admin":
                return _deny(403, "FORBIDDEN", "Only administrators can do this.")

            match = MEETING_PATH.match(path)
            if match and user.role != "admin":
                meeting = db.query(MeetingDB).filter(MeetingDB.id == match.group(1)).first()
                # A missing meeting falls through so the route answers 404 itself.
                if meeting is not None and meeting.owner_id != user.id:
                    return _deny(403, "FORBIDDEN", "You do not have access to this meeting.")
        finally:
            session_source.close()
        return await call_next(request)


def current_user(request: Request) -> Optional[dict]:
    """The signed-in user's {id, role, email, name}, or None when checks are off."""
    return getattr(request.state, "user", None)


def is_admin(user: Optional[dict]) -> bool:
    # With checks switched off there is no user; behave like the old open API.
    return user is None or user["role"] == "admin"


def delete_meeting_data(db: Session, meeting: MeetingDB) -> None:
    """Remove a meeting, its rows and its audio files."""
    for audio in db.query(AudioDB).filter(AudioDB.meeting_id == meeting.id).all():
        Path(audio.file_path).unlink(missing_ok=True)
    for model in (MinutesVersionDB, ReminderSentDB, MinutesDB, TranscriptDB, AudioDB, MeetingMetaDB):
        db.query(model).filter(model.meeting_id == meeting.id).delete()
    db.delete(meeting)
    db.commit()


# ---------------------------------------------------------------- endpoints
router = APIRouter(tags=["auth"])


class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(max_length=320)
    password: str = Field(min_length=8, max_length=200)


class LoginIn(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=200)


class RefreshIn(BaseModel):
    refresh_token: str = Field(max_length=500)


class LogoutIn(BaseModel):
    refresh_token: str = Field(default="", max_length=500)


class RoleIn(BaseModel):
    role: str


def _user_out(user: UserDB) -> dict:
    return {"id": user.id, "name": user.name, "email": user.email, "role": user.role}


def _actor(user: UserDB) -> dict:
    return {"id": user.id, "email": user.email}


@router.post("/auth/register", status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    name = security.sanitize_text(body.name).strip()
    if not name or not EMAIL_RE.match(email):
        return _deny(400, "INVALID", "Enter your name and a valid email address.")
    if db.query(UserDB).filter(UserDB.email == email).first() is not None:
        return _deny(409, "EXISTS", "An account with this email already exists.")
    first_user = db.query(UserDB).count() == 0
    user = UserDB(
        id=str(uuid4()),
        email=email,
        name=name,
        password_hash=hash_password(body.password),
        role="admin" if first_user else "user",
    )
    db.add(user)
    # Meetings made before login existed belong to the first account.
    if first_user:
        db.query(MeetingDB).filter(MeetingDB.owner_id.is_(None)).update({"owner_id": user.id})
    db.commit()
    audit.log(db, "register", _actor(user), f"role={user.role}")
    return issue(db, user)


@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    user = db.query(UserDB).filter(UserDB.email == email).first()
    wrong = _deny(401, "BAD_CREDENTIALS", "Email or password is wrong.")
    if user is None:
        audit.log(db, "login-failed", None, f"unknown email {email[:80]}")
        return wrong

    now = _now()
    locked_until = _aware(user.locked_until)
    if locked_until is not None and locked_until > now:
        minutes = int((locked_until - now).total_seconds() // 60) + 1
        return _deny(429, "LOCKED", f"Too many wrong passwords. Try again in {minutes} minute(s).")

    if not verify_password(body.password, user.password_hash):
        user.failed_attempts += 1
        locked = user.failed_attempts >= MAX_FAILED_ATTEMPTS
        if locked:
            user.locked_until = now + timedelta(minutes=LOCK_MINUTES)
            user.failed_attempts = 0
        db.commit()
        audit.log(db, "account-locked" if locked else "login-failed", _actor(user), "")
        return wrong

    user.failed_attempts = 0
    user.locked_until = None
    if not user.password_hash.startswith("$argon2"):
        user.password_hash = hash_password(body.password)   # upgrade an older hash
    db.commit()
    audit.log(db, "login", _actor(user), "")
    return issue(db, user)


@router.post("/auth/refresh")
def refresh(body: RefreshIn, db: Session = Depends(get_db)):
    """Swap a refresh token for a new access token and a new refresh token (rotation)."""
    expired = _deny(401, "UNAUTHENTICATED", "Your session has expired. Please log in again.")
    session = db.query(SessionDB).filter(SessionDB.refresh_hash == _hash_refresh(body.refresh_token)).first()
    if session is None:
        return expired
    user = db.query(UserDB).filter(UserDB.id == session.user_id).first()
    if session.revoked:
        # An old refresh token was presented again: someone may have copied it. End all sessions.
        db.query(SessionDB).filter(SessionDB.user_id == session.user_id).update({"revoked": True})
        db.commit()
        if user:
            audit.log(db, "refresh-token-reuse", _actor(user), "all sessions revoked")
        return expired
    if user is None or _aware(session.expires_at) < _now():
        return expired
    session.revoked = True
    db.commit()
    return issue(db, user)


@router.post("/auth/logout")
def logout(request: Request, body: LogoutIn, db: Session = Depends(get_db)):
    """End the session: its refresh token and access tokens stop working."""
    header = request.headers.get("authorization", "")
    claims = read_token(header[7:]) if header.lower().startswith("bearer ") else None
    sessions = []
    if claims and claims.get("sid"):
        sessions += db.query(SessionDB).filter(SessionDB.id == claims["sid"]).all()
    if body.refresh_token:
        sessions += db.query(SessionDB).filter(SessionDB.refresh_hash == _hash_refresh(body.refresh_token)).all()
    for session in sessions:
        session.revoked = True
    db.commit()
    for session in sessions[:1]:
        user = db.query(UserDB).filter(UserDB.id == session.user_id).first()
        if user:
            audit.log(db, "logout", _actor(user), "")
    return {"ok": True}


@router.get("/auth/me")
def me(request: Request, db: Session = Depends(get_db)):
    header = request.headers.get("authorization", "")
    claims = read_token(header[7:]) if header.lower().startswith("bearer ") else None
    user = db.query(UserDB).filter(UserDB.id == claims["sub"]).first() if claims else None
    if user is None:
        return _deny(401, "UNAUTHENTICATED", "Your session has expired. Please log in again.")
    return _user_out(user)


@router.get("/admin/users")
def list_users(db: Session = Depends(get_db)):
    """Administrators only (checked by AuthMiddleware)."""
    return [_user_out(u) for u in db.query(UserDB).order_by(UserDB.created_at).all()]


@router.put("/admin/users/{user_id}/role")
def change_role(user_id: str, body: RoleIn, request: Request, db: Session = Depends(get_db)):
    """Administrators only: make someone an admin or a normal user."""
    if body.role not in {"admin", "user"}:
        return _deny(400, "INVALID", "The role must be admin or user.")
    target = db.query(UserDB).filter(UserDB.id == user_id).first()
    if target is None:
        return _deny(404, "NOT_FOUND", "User not found.")
    if target.role == "admin" and body.role == "user":
        if db.query(UserDB).filter(UserDB.role == "admin").count() <= 1:
            return _deny(409, "LAST_ADMIN", "There must be at least one administrator.")
    old = target.role
    target.role = body.role
    db.commit()
    audit.log(db, "role-change", current_user(request), f"{target.email}: {old} -> {body.role}")
    return _user_out(target)
