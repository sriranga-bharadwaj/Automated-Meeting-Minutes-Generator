"""Consolidated API under /api/v1, used by the React frontend and client integrations.

Flow: create meeting -> upload audio (starts background job) ->
poll /status -> read /minutes -> edit/save minutes -> export (DOCX/PDF/Markdown).
"""
import json
import os
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, File, Response, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app import export, jobs
from app.database import get_db
from app.minutes_adapter import to_ui_minutes
from app.models import AudioDB, MeetingDB, MeetingMetaDB, MinutesDB

router = APIRouter(prefix="/api/v1", tags=["meetings"])

AUDIO_UPLOAD_DIR = Path("uploads/audio")
AUDIO_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_AUDIO_TYPES = {".mp3", ".wav", ".m4a", ".ogg", ".webm", ".mp4"}
MAX_AUDIO_BYTES = int(os.getenv("MAX_AUDIO_MB", "500")) * 1024 * 1024


class Attendee(BaseModel):
    name: str = ""
    email: str = ""


class MeetingInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    datetime: str = ""
    agenda: str = Field(default="", max_length=5000)
    language: str = "en"
    attendees: list[Attendee] = Field(default_factory=list)


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"code": code, "message": message, "detail": message})


def _get_meeting(db: Session, meeting_id: str) -> Optional[MeetingDB]:
    return db.query(MeetingDB).filter(MeetingDB.id == meeting_id).first()


def _latest_audio(db: Session, meeting_id: str) -> Optional[AudioDB]:
    return (
        db.query(AudioDB)
        .filter(AudioDB.meeting_id == meeting_id)
        .order_by(AudioDB.created_at.desc())
        .first()
    )


def _latest_minutes(db: Session, meeting_id: str) -> Optional[MinutesDB]:
    return (
        db.query(MinutesDB)
        .filter(MinutesDB.meeting_id == meeting_id)
        .order_by(MinutesDB.created_at.desc())
        .first()
    )


def _stored_ui_minutes(db: Session, meeting: MeetingDB, row: MinutesDB) -> dict:
    """The stored wrapper {'format': 'ui-v1', 'minutes': ...}; rows written by older
    data are converted on the fly."""
    stored = json.loads(row.content_json)
    if stored.get("format") == "ui-v1":
        return stored
    return {
        "format": "ui-v1",
        "minutes": to_ui_minutes(stored, jobs.load_meta(db, meeting)),
        "raw": stored,
    }


@router.post("/meetings", status_code=201)
def create_meeting(body: dict = Body(...), db: Session = Depends(get_db)):
    try:
        data = MeetingInput.model_validate(body)
    except ValidationError:
        return _error(400, "INVALID", "Some of the details are invalid.")
    title = data.title.strip()
    if not title:
        return _error(400, "INVALID", "The meeting title cannot be blank.")

    attendees = [
        {"name": a.name.strip(), "email": a.email.strip()}
        for a in data.attendees if a.name.strip()
    ]
    meeting_id = str(uuid4())
    db.add(MeetingDB(id=meeting_id, title=title, description=data.agenda.strip(), status="created"))
    db.add(
        MeetingMetaDB(
            meeting_id=meeting_id,
            meta_json=json.dumps(
                {
                    "title": title,
                    "datetime": data.datetime,
                    "agenda": data.agenda.strip(),
                    "language": data.language,
                    "attendees": attendees,
                },
                ensure_ascii=False,
            ),
        )
    )
    db.commit()
    return {
        "meetingId": meeting_id,
        "id": meeting_id,
        "title": title,
        "description": data.agenda.strip(),
        "status": "created",
    }


@router.get("/meetings")
def list_meetings(db: Session = Depends(get_db)):
    meetings = db.query(MeetingDB).order_by(MeetingDB.created_at.desc()).all()
    return [
        {
            "id": m.id,
            "meetingId": m.id,
            "title": m.title,
            "description": m.description,
            "status": m.status,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in meetings
    ]


@router.get("/meetings/{meeting_id}")
def get_meeting(meeting_id: str, db: Session = Depends(get_db)):
    meeting = _get_meeting(db, meeting_id)
    if meeting is None:
        return _error(404, "NOT_FOUND", "Meeting not found.")
    return {
        "id": meeting.id,
        "meetingId": meeting.id,
        "title": meeting.title,
        "description": meeting.description,
        "status": meeting.status,
        "created_at": meeting.created_at.isoformat() if meeting.created_at else None,
    }


@router.post("/meetings/{meeting_id}/audio", status_code=201)
async def upload_audio(meeting_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    if _get_meeting(db, meeting_id) is None:
        return _error(404, "NOT_FOUND", "Meeting not found.")
    
    raw_filename = file.filename or ""
    # Safe extension extraction
    extension = Path(raw_filename).suffix.lower()
    if extension not in ALLOWED_AUDIO_TYPES:
        return _error(415, "UNSUPPORTED", "This file type is not supported.")

    # Prevent path traversal by isolating storage under a random UUID name
    audio_id = str(uuid4())
    safe_filename = Path(raw_filename).name or f"{audio_id}{extension}"
    destination = AUDIO_UPLOAD_DIR / f"{audio_id}{extension}"
    size = 0
    rejected: Optional[JSONResponse] = None
    try:
        with destination.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_AUDIO_BYTES:
                    rejected = _error(413, "TOO_LARGE", "The file is too large.")
                    break
                out.write(chunk)
        if rejected is None and size == 0:
            rejected = _error(400, "EMPTY", "The audio file is empty.")
        if rejected is not None:
            destination.unlink(missing_ok=True)
            return rejected
        db.add(
            AudioDB(
                id=audio_id,
                meeting_id=meeting_id,
                filename=safe_filename,
                file_path=str(destination),
                size_bytes=size,
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        destination.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    if not jobs.is_running(meeting_id):
        jobs.submit(meeting_id)  # processing starts as soon as the audio is in
    return {"status": "uploaded", "audioId": audio_id, "audio_id": audio_id}


@router.post("/meetings/{meeting_id}/process", status_code=202)
def process_meeting(meeting_id: str, db: Session = Depends(get_db)):
    """Start or verify background transcription + minutes generation."""
    if _get_meeting(db, meeting_id) is None:
        return _error(404, "NOT_FOUND", "Meeting not found.")
    if _latest_audio(db, meeting_id) is None:
        return _error(404, "NO_AUDIO", "No audio has been uploaded for this meeting.")
    if not jobs.is_running(meeting_id):
        jobs.submit(meeting_id)
    return {"meeting_id": meeting_id, "status": "QUEUED"}


@router.get("/meetings/{meeting_id}/status")
def get_status(meeting_id: str, db: Session = Depends(get_db)):
    if _get_meeting(db, meeting_id) is None:
        return _error(404, "NOT_FOUND", "Meeting not found.")
    info = jobs.get_status(meeting_id)
    if info is not None:
        return info
    # No in-memory state: the server restarted, or nothing was uploaded yet.
    if _latest_minutes(db, meeting_id) is not None:
        return {"status": "READY", "stage": "Minutes ready", "progress": 100}
    if _latest_audio(db, meeting_id) is not None:
        return {
            "status": "FAILED", "stage": "", "progress": 0,
            "error": "Processing was interrupted. Please retry.",
        }
    return {"status": "QUEUED", "stage": "Waiting for the audio upload", "progress": 0}


@router.post("/meetings/{meeting_id}/retry", status_code=202)
def retry(meeting_id: str, db: Session = Depends(get_db)):
    if _get_meeting(db, meeting_id) is None:
        return _error(404, "NOT_FOUND", "Meeting not found.")
    if _latest_audio(db, meeting_id) is None:
        return _error(400, "NO_AUDIO", "No audio has been uploaded for this meeting.")
    if not jobs.is_running(meeting_id):
        jobs.submit(meeting_id)
    return {"status": "queued"}


@router.get("/meetings/{meeting_id}/minutes")
def get_minutes(meeting_id: str, db: Session = Depends(get_db)):
    meeting = _get_meeting(db, meeting_id)
    if meeting is None:
        return _error(404, "NOT_FOUND", "Meeting not found.")
    row = _latest_minutes(db, meeting_id)
    if row is None:
        return _error(404, "NOT_READY", "The minutes are not ready yet.")
    return _stored_ui_minutes(db, meeting, row)["minutes"]


def _save_minutes_impl(meeting_id: str, body: dict, db: Session):
    content = body.get("content")
    if not isinstance(content, dict):
        return _error(400, "INVALID", "Some of the details are invalid.")
    meeting = _get_meeting(db, meeting_id)
    row = _latest_minutes(db, meeting_id) if meeting is not None else None
    if meeting is None or row is None:
        return _error(404, "NOT_FOUND", "Minutes not found.")

    stored = _stored_ui_minutes(db, meeting, row)
    try:
        current = int(stored["minutes"].get("version", 1))
    except (TypeError, ValueError):
        current = 1

    if "version" in content and content.get("version") != current:
        return _error(
            409,
            "CONFLICT",
            "Someone else changed these minutes. Reload to see the latest version.",
        )

    version = current + 1
    content["version"] = version
    stored["minutes"] = content
    row.content_json = json.dumps(stored, ensure_ascii=False)
    db.commit()
    return {"version": version}


@router.put("/minutes/{meeting_id}")
def save_minutes_legacy(meeting_id: str, body: dict = Body(...), db: Session = Depends(get_db)):
    return _save_minutes_impl(meeting_id, body, db)


@router.put("/meetings/{meeting_id}/minutes")
def save_minutes(meeting_id: str, body: dict = Body(...), db: Session = Depends(get_db)):
    return _save_minutes_impl(meeting_id, body, db)


@router.post("/meetings/{meeting_id}/export")
def export_minutes(
    meeting_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
):
    meeting = _get_meeting(db, meeting_id)
    if meeting is None:
        return _error(404, "NOT_FOUND", "Meeting not found.")

    fmt = payload.get("format", "md").lower()
    if fmt not in ("docx", "pdf", "md"):
        return _error(400, "INVALID_FORMAT", "Unsupported export format.")

    minutes = payload.get("content")
    if minutes is None:
        row = _latest_minutes(db, meeting_id)
        if row is None:
            return _error(404, "NOT_READY", "The minutes are not ready to export.")
        minutes = _stored_ui_minutes(db, meeting, row)["minutes"]

    data, media_type, filename = export.render(minutes, fmt)
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
