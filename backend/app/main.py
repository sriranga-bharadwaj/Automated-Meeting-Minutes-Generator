
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app import audit, auth, crypto, export, features, pipeline, security, sources, versions
from app.audio_check import AudioCheckError, check_audio_file
from app.database import Base, engine, ensure_schema, get_db
from app.models import AudioDB, MeetingDB, MinutesDB, TranscriptDB, UserDB
from app.minutes_generator import generate_minutes
from app.transcription import (
    AudioPreprocessingError,
    UnsupportedAudioFormatError,
    transcribe_audio,
)
from app.ui_schema import ExportRequest, SaveMinutesRequest

from app.api_v1 import router as api_v1_router


logger = logging.getLogger(__name__)

AUDIO_UPLOAD_DIR = Path("uploads/audio")
AUDIO_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_AUDIO_SIZE = 25 * 1024 * 1024

ALLOWED_AUDIO_TYPES = {
    ".mp3",
    ".wav",
    ".m4a",
    ".ogg",
    ".webm",
    ".mp4",
}

Base.metadata.create_all(bind=engine)
ensure_schema()

@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Hourly background loop: deadline reminders, retention purge, audit-log purge.
    features.start_scheduler()
    yield


app = FastAPI(
    title="Automated Meeting Minutes Generator",
    description="API for generating structured meeting minutes from audio.",
    version="0.6.0",
    lifespan=lifespan,
)

# The React dev server normally reaches the API through its own proxy; CORS
# is only needed if someone opens the API from the dev server's address directly.
# Middleware order: the one added last runs first. Security headers wrap everything (also
# the 401 and 429 answers), CORS comes next, and the login/rate-limit/ownership checks are innermost.
app.add_middleware(auth.AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(security.SecurityHeadersMiddleware)

app.include_router(api_v1_router)
app.include_router(auth.router)                     # /auth/..., /admin/users
app.include_router(auth.router, prefix="/api/v1")   # same routes under /api/v1
app.include_router(features.router)                 # transcript, versions, share, actions, admin console
app.include_router(features.router, prefix="/api/v1")


class AttendeeIn(BaseModel):
    name: str = Field(max_length=200)
    email: str = Field(default="", max_length=320)


class MeetingCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    # Optional details collected by the web form
    scheduled_for: str = Field(default="", max_length=40, alias="datetime")
    agenda: str = Field(default="", max_length=5000)
    language: str = Field(default="", max_length=10)
    attendees: list[AttendeeIn] = Field(default_factory=list, max_length=100)


class Meeting(BaseModel):
    id: str
    title: str
    description: str
    status: str
    created_at: datetime
    owner_email: str | None = None  # who owns it (shown in the meeting list)
    owned: bool = True              # False: the person was invited and can only view it


@app.get("/")
def root():
    return {
        "message": "Automated Meeting Minutes Generator API is running",
        "status": "healthy",
    }


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post(
    "/meetings",
    response_model=Meeting,
    status_code=status.HTTP_201_CREATED,
)
def create_meeting(
    payload: MeetingCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    title = security.sanitize_text(payload.title).strip()
    user = auth.current_user(request)

    if not title:
        raise HTTPException(
            status_code=422,
            detail="Meeting title cannot be blank.",
        )

    meeting = MeetingDB(
        id=str(uuid4()),
        title=title,
        description=security.sanitize_text(payload.description).strip(),
        status="created",
        owner_id=user["id"] if user else None,
        created_at=datetime.now(timezone.utc),
        details_json=json.dumps(
            security.sanitize_obj({
                "datetime": payload.scheduled_for,
                "agenda": payload.agenda.strip(),
                "language": payload.language,
                "attendees": [a.model_dump() for a in payload.attendees],
            }),
            ensure_ascii=False,
        ),
    )

    db.add(meeting)
    db.commit()
    db.refresh(meeting)
    return meeting


@app.get("/meetings", response_model=list[Meeting])
def list_meetings(request: Request, db: Session = Depends(get_db)):
    """An administrator sees every meeting. Everyone else sees the meetings they own and the ones
    they were invited to (their email is in the attendee list); invited ones have owned=False."""
    user = auth.current_user(request)
    emails = {u.id: u.email for u in db.query(UserDB).all()}
    out = []
    for m in db.query(MeetingDB).order_by(MeetingDB.created_at.desc()).all():
        owned = user is None or user["role"] == "admin" or m.owner_id == user["id"]
        if not owned and not auth.is_invited(db, m, user["email"]):
            continue
        out.append(
            Meeting(
                id=m.id, title=m.title, description=m.description, status=m.status,
                created_at=m.created_at, owner_email=emails.get(m.owner_id), owned=owned,
            )
        )
    return out


@app.get("/meetings/{meeting_id}", response_model=Meeting)
def get_meeting(meeting_id: str, db: Session = Depends(get_db)):
    meeting = (
        db.query(MeetingDB)
        .filter(MeetingDB.id == meeting_id)
        .first()
    )

    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found.")

    return meeting


@app.delete("/meetings/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meeting(meeting_id: str, request: Request, db: Session = Depends(get_db)):
    """Delete a meeting and its audio. The owner or an administrator may do this."""
    meeting = db.query(MeetingDB).filter(MeetingDB.id == meeting_id).first()
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found.")
    title = meeting.title
    auth.delete_meeting_data(db, meeting)
    audit.log(db, "meeting-delete", auth.current_user(request), f"{meeting_id} ({title[:80]})")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post(
    "/meetings/{meeting_id}/audio",
    status_code=status.HTTP_201_CREATED,
)
async def upload_meeting_audio(
    meeting_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    try:
        meeting = (
            db.query(MeetingDB)
            .filter(MeetingDB.id == meeting_id)
            .first()
        )

        if meeting is None:
            raise HTTPException(
                status_code=404,
                detail="Meeting not found.",
            )

        extension = Path(file.filename or "").suffix.lower()

        if extension not in ALLOWED_AUDIO_TYPES:
            raise HTTPException(
                status_code=400,
                detail="Unsupported audio file type.",
            )

        audio_id = str(uuid4())
        destination = AUDIO_UPLOAD_DIR / f"{audio_id}{extension}"
        size = 0

        try:
            with destination.open("wb") as audio_file:
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break

                    size += len(chunk)
                    if size > MAX_AUDIO_SIZE:
                        raise HTTPException(
                            status_code=413,
                            detail="Audio file exceeds the 25 MB limit.",
                        )

                    audio_file.write(chunk)

            try:
                check_audio_file(str(destination), file.content_type, extension)
            except AudioCheckError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            crypto.encrypt_file(destination)   # audio is encrypted at rest

            audio_record = AudioDB(
                id=audio_id,
                meeting_id=meeting_id,
                filename=file.filename or destination.name,
                file_path=str(destination),
                size_bytes=size,
            )
            db.add(audio_record)
            db.commit()

        except Exception:
            db.rollback()
            destination.unlink(missing_ok=True)
            raise

        return {
            "message": "Audio uploaded successfully.",
            "meeting_id": meeting_id,
            "audio_id": audio_id,
            "filename": file.filename,
            "size_bytes": size,
            "status": "uploaded",
        }
    finally:
        await file.close()


@app.post("/meetings/{meeting_id}/transcribe")
def transcribe_meeting(
    meeting_id: str,
    db: Session = Depends(get_db),
):
    try:
        meeting = (
            db.query(MeetingDB)
            .filter(MeetingDB.id == meeting_id)
            .first()
        )

        if meeting is None:
            raise HTTPException(
                status_code=404,
                detail="Meeting not found.",
            )

        audio = (
            db.query(AudioDB)
            .filter(AudioDB.meeting_id == meeting_id)
            .order_by(AudioDB.created_at.desc())
            .first()
        )

        if audio is None:
            raise HTTPException(
                status_code=404,
                detail="No audio uploaded for this meeting.",
            )

        transcription = transcribe_audio(audio.file_path)
        transcript_text = transcription["text"].strip()

        if not transcript_text:
            raise HTTPException(
                status_code=422,
                detail="No speech was detected in the audio.",
            )

        minutes = generate_minutes(
            transcript_text,
            segments=transcription.get("segments"),
        )

        transcript_record, minutes_record = pipeline.persist_result(
            db, meeting, audio, transcription, minutes
        )
        db.commit()

        return {
            "message": "Transcription and minutes generated successfully.",
            "meeting_id": meeting_id,
            "transcript_id": transcript_record.id,
            "minutes_id": minutes_record.id,
            "language": transcription.get("language"),
            "transcript": transcript_text,
            "minutes": minutes,
            "status": meeting.status,
        }

    except HTTPException:
        db.rollback()
        raise

    except FileNotFoundError:
        db.rollback()
        raise HTTPException(
            status_code=404,
            detail="Uploaded audio file could not be found.",
        )

    except UnsupportedAudioFormatError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    except AudioPreprocessingError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    except Exception as exc:
        db.rollback()
        logger.exception("Transcription/minutes generation failed")
        raise HTTPException(
            status_code=500,
            detail=(
                "Transcription/minutes generation failed: "
                f"{type(exc).__name__}: {exc}"
            ),
        ) from exc



# ---------------------------------------------------------------------------
# Endpoints used by the web UI: background processing, minutes, export
# ---------------------------------------------------------------------------
def _get_meeting_or_404(db: Session, meeting_id: str) -> MeetingDB:
    meeting = db.query(MeetingDB).filter(MeetingDB.id == meeting_id).first()
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found.")
    return meeting


def _start_processing(
    meeting_id: str,
    background_tasks: BackgroundTasks,
    db: Session,
):
    _get_meeting_or_404(db, meeting_id)
    has_audio = db.query(AudioDB).filter(AudioDB.meeting_id == meeting_id).first()
    if has_audio is None:
        raise HTTPException(status_code=404, detail="No audio uploaded for this meeting.")

    if not pipeline.is_running(meeting_id):
        pipeline.set_job(meeting_id, "QUEUED", 0, "Waiting to start")
        background_tasks.add_task(pipeline.run_job, meeting_id)
    return {"meeting_id": meeting_id, "status": "QUEUED"}


@app.post("/meetings/{meeting_id}/process", status_code=status.HTTP_202_ACCEPTED)
def process_meeting(
    meeting_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Start transcription + minutes generation in the background."""
    return _start_processing(meeting_id, background_tasks, db)


@app.post("/meetings/{meeting_id}/retry", status_code=status.HTTP_202_ACCEPTED)
def retry_meeting(
    meeting_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Run processing again after a failure."""
    return _start_processing(meeting_id, background_tasks, db)


@app.get("/meetings/{meeting_id}/status")
def meeting_status(meeting_id: str, db: Session = Depends(get_db)):
    meeting = _get_meeting_or_404(db, meeting_id)
    job = pipeline.status_for(meeting)
    result = {
        "status": job["status"],
        "progress": job["progress"],
        "stage": job["stage"] or None,
    }
    if job["error"]:
        result["error"] = job["error"]
    return result


@app.get("/meetings/{meeting_id}/minutes")
def get_minutes(meeting_id: str, db: Session = Depends(get_db)):
    meeting = _get_meeting_or_404(db, meeting_id)
    found = pipeline.current_ui_minutes(db, meeting)
    if found is None:
        raise HTTPException(status_code=404, detail="Minutes have not been generated yet.")
    # Each item gets a "source" (seconds in the recording) when it can be linked to the transcript.
    return sources.attach(found[0], features.segments_for(db, meeting_id))


@app.put("/meetings/{meeting_id}/minutes")
def save_minutes(
    meeting_id: str,
    payload: SaveMinutesRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    meeting = _get_meeting_or_404(db, meeting_id)
    found = pipeline.current_ui_minutes(db, meeting)
    if found is None:
        raise HTTPException(status_code=404, detail="Minutes have not been generated yet.")
    current, row = found

    if payload.content.version != current["version"]:
        raise HTTPException(
            status_code=409,
            detail="Someone else changed these minutes. Reload to see the latest version.",
        )

    new_version = current["version"] + 1
    user = auth.current_user(request)
    versions.archive(db, meeting_id, current, current["version"], user["email"] if user else None)
    content = security.sanitize_obj(payload.content.model_dump())
    content["version"] = new_version
    row.content_json = json.dumps(content, ensure_ascii=False)
    db.commit()
    return {"version": new_version}


@app.post("/meetings/{meeting_id}/export")
def export_minutes(
    meeting_id: str,
    payload: ExportRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    meeting = _get_meeting_or_404(db, meeting_id)
    audit.log(db, "export", auth.current_user(request), f"{meeting_id} as {payload.format}")
    if payload.content is not None:
        minutes = payload.content.model_dump()
    else:
        found = pipeline.current_ui_minutes(db, meeting)
        if found is None:
            raise HTTPException(status_code=404, detail="Minutes have not been generated yet.")
        minutes = found[0]

    data, media_type, filename = export.render(minutes, payload.format)
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
