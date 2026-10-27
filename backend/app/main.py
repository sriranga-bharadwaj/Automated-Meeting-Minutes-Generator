
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.models import MeetingDB


AUDIO_UPLOAD_DIR = Path("uploads/audio")
AUDIO_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_AUDIO_SIZE = 25 * 1024 * 1024  # 25 MB

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
    version="0.3.0",
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
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
    return (
        db.query(MeetingDB)
        .order_by(MeetingDB.created_at.desc())
        .all()
    )


@app.get("/meetings/{meeting_id}", response_model=Meeting)
def get_meeting(
    meeting_id: str,
    db: Session = Depends(get_db),
):
    meeting = (
        db.query(MeetingDB)
        .filter(MeetingDB.id == meeting_id)
        .first()
    )

    if meeting is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found.",
        )

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
    meeting = (
        db.query(MeetingDB)
        .filter(MeetingDB.id == meeting_id)
        .first()
    )

    if meeting is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found.",
        )

    extension = Path(file.filename or "").suffix.lower()

    if extension not in ALLOWED_AUDIO_TYPES:
        await file.close()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
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
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="Audio file exceeds the 25 MB limit.",
                    )

                audio_file.write(chunk)

    except Exception:
        destination.unlink(missing_ok=True)
        raise

    finally:
        await file.close()

    return {
        "message": "Audio uploaded successfully.",
        "meeting_id": meeting_id,
        "audio_id": audio_id,
        "filename": file.filename,
        "size_bytes": size,
        "status": "uploaded",
    }
