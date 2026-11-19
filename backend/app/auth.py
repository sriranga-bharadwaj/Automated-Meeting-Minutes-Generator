"""Login, roles and per-user access to meetings.

- Passwords are stored as scrypt hashes (standard library, no extra package).
- Login returns a signed token (HS256 JWT built with hmac) that the web UI sends as
  "Authorization: Bearer <token>".
- Roles: "user" sees and changes only their own meetings; "admin" sees all meetings,
  can delete any meeting and can list users. The first account registered becomes admin.
- Five wrong passwords lock an account for 15 minutes.
- Set AUTH_REQUIRED=false to switch the checks off (used by the older tests and for demos).
  Set AMMG_SECRET_KEY to fix the token signing key; otherwise one is created in .ammg_secret.
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

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

from app.database import get_db
from app.models import AudioDB, MeetingDB, MeetingMetaDB, MinutesDB, TranscriptDB, UserDB

TOKEN_LIFETIME_SECONDS = 8 * 60 * 60
MAX_FAILED_ATTEMPTS = 5
LOCK_MINUTES = 15
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def auth_required() -> bool:
    return os.getenv("AUTH_REQUIRED", "true").strip().lower() not in {"0", "false", "no", "off"}


# ---------------------------------------------------------------- passwords and tokens
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1, dklen=32
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


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


def make_token(user: UserDB) -> str:
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64(
        json.dumps(
            {"sub": user.id, "role": user.role, "exp": int(time.time()) + TOKEN_LIFETIME_SECONDS}
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


# ---------------------------------------------------------------- request checks
PUBLIC_PATHS = {"/", "/health", "/docs", "/redoc", "/openapi.json"}
MEETING_PATH = re.compile(r"^(?:/api/v1)?/(?:meetings|minutes)/([^/]+)")


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
    """Checks the token on every request and the owner on every per-meeting request."""

    async def dispatch(self, request: Request, call_next):
        request.state.user = None
        if request.method == "OPTIONS" or not auth_required() or _is_public(request.url.path):
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
            if user is None:
                return _deny(401, "UNAUTHENTICATED", "Your session has expired. Please log in again.")
            request.state.user = {"id": user.id, "role": user.role, "email": user.email, "name": user.name}

            path = request.url.path
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
    for model in (MinutesDB, TranscriptDB, AudioDB, MeetingMetaDB):
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


def _user_out(user: UserDB) -> dict:
    return {"id": user.id, "name": user.name, "email": user.email, "role": user.role}


@router.post("/auth/register", status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    name = body.name.strip()
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
    return {"token": make_token(user), "user": _user_out(user)}


@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.email == body.email.strip().lower()).first()
    wrong = _deny(401, "BAD_CREDENTIALS", "Email or password is wrong.")
    if user is None:
        return wrong

    now = datetime.now(timezone.utc)
    locked_until = user.locked_until
    if locked_until is not None and locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=timezone.utc)
    if locked_until is not None and locked_until > now:
        minutes = int((locked_until - now).total_seconds() // 60) + 1
        return _deny(429, "LOCKED", f"Too many wrong passwords. Try again in {minutes} minute(s).")

    if not verify_password(body.password, user.password_hash):
        user.failed_attempts += 1
        if user.failed_attempts >= MAX_FAILED_ATTEMPTS:
            user.locked_until = now + timedelta(minutes=LOCK_MINUTES)
            user.failed_attempts = 0
        db.commit()
        return wrong

    user.failed_attempts = 0
    user.locked_until = None
    db.commit()
    return {"token": make_token(user), "user": _user_out(user)}


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
