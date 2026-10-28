
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.models import AudioDB, MeetingDB, MinutesDB, TranscriptDB
from app.minutes_generator import generate_minutes
from app.transcription import transcribe_audio


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

app = FastAPI(
    title="Automated Meeting Minutes Generator",
    description="API for generating structured meeting minutes from audio.",
    version="0.4.0",
)


class MeetingCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)


class Meeting(BaseModel):
    id: str
    title: str
    description: str
    status: str
    created_at: datetime


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
    db: Session = Depends(get_db),
):
    title = payload.title.strip()

    if not title:
        raise HTTPException(
            status_code=422,
            detail="Meeting title cannot be blank.",
        )

    meeting = MeetingDB(
        id=str(uuid4()),
        title=title,
        description=payload.description.strip(),
        status="created",
        created_at=datetime.now(timezone.utc),
    )

    db.add(meeting)
    db.commit()
    db.refresh(meeting)
    return meeting


@app.get("/meetings", response_model=list[Meeting])
def list_meetings(db: Session = Depends(get_db)):
    return db.query(MeetingDB).order_by(MeetingDB.created_at.desc()).all()


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

        minutes = generate_minutes(transcript_text)

        transcript_record = TranscriptDB(
            id=str(uuid4()),
            meeting_id=meeting_id,
            audio_id=audio.id,
            text=transcript_text,
            language=transcription.get("language"),
            segments_json=json.dumps(
                transcription.get("segments", []),
                ensure_ascii=False,
            ),
        )
        db.add(transcript_record)
        db.flush()

        minutes_record = MinutesDB(
            id=str(uuid4()),
            meeting_id=meeting_id,
            transcript_id=transcript_record.id,
            content_json=json.dumps(minutes, ensure_ascii=False),
        )
        db.add(minutes_record)

        meeting.status = "processed"
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
