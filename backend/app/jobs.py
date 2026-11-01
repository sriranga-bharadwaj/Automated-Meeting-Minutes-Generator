"""Background processing for the /api/v1 endpoints.

A single worker thread runs jobs one after another: transcription and the LLM
both need a lot of CPU and RAM, so two recordings at once would only slow each
other down. Status is kept in memory and is lost when the server restarts
(app/api_v1.py handles that case).
"""
import json
import logging
import queue
import threading
from typing import Optional
from uuid import uuid4

from app.database import SessionLocal
from app.minutes_adapter import to_ui_minutes
from app.minutes_generator import generate_minutes
from app.models import AudioDB, MeetingDB, MeetingMetaDB, MinutesDB, TranscriptDB
from app.transcription import TranscriptionError, transcribe_audio

logger = logging.getLogger(__name__)

RUNNING = ("QUEUED", "TRANSCRIBING", "ANALYSING")

_lock = threading.Lock()
_status: dict[str, dict] = {}
_queue: queue.Queue = queue.Queue()
_worker: Optional[threading.Thread] = None


class ProcessingError(Exception):
    """A problem whose message is safe to show to the user."""


def set_status(meeting_id: str, status: str, stage: str = "", progress: int = 0, error: Optional[str] = None):
    info = {"status": status, "stage": stage, "progress": progress}
    if error:
        info["error"] = error
    with _lock:
        _status[meeting_id] = info


def get_status(meeting_id: str) -> Optional[dict]:
    with _lock:
        info = _status.get(meeting_id)
        return dict(info) if info else None


def is_running(meeting_id: str) -> bool:
    info = get_status(meeting_id)
    return bool(info) and info["status"] in RUNNING


def load_meta(db, meeting) -> dict:
    row = db.query(MeetingMetaDB).filter(MeetingMetaDB.meeting_id == meeting.id).first()
    meta: dict = {}
    if row is not None:
        try:
            meta = json.loads(row.meta_json)
        except ValueError:
            meta = {}
    meta.setdefault("title", meeting.title)
    meta.setdefault("datetime", "")
    meta.setdefault("agenda", meeting.description or "")
    meta.setdefault("language", "en")
    meta.setdefault("attendees", [])
    return meta


def _run_worker():
    while True:
        meeting_id, factory = _queue.get()
        try:
            run_job(meeting_id, factory)
        except Exception:  # run_job handles its own errors; this is a last resort
            logger.exception("Unexpected worker error")
        finally:
            _queue.task_done()


def submit(meeting_id: str, session_factory=None):
    global _worker
    set_status(meeting_id, "QUEUED", "Waiting for a worker", 5)
    with _lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_run_worker, name="minutes-worker", daemon=True)
            _worker.start()
    _queue.put((meeting_id, session_factory))


def run_job(meeting_id: str, session_factory=None):
    db = (session_factory or SessionLocal)()
    progress = 0
    try:
        meeting = db.query(MeetingDB).filter(MeetingDB.id == meeting_id).first()
        audio = (
            db.query(AudioDB)
            .filter(AudioDB.meeting_id == meeting_id)
            .order_by(AudioDB.created_at.desc())
            .first()
        )
        if meeting is None or audio is None:
            raise ProcessingError("No audio was found for this meeting.")
        meta = load_meta(db, meeting)

        progress = 10
        set_status(meeting_id, "TRANSCRIBING", "Converting speech to text", progress)
        transcription = transcribe_audio(audio.file_path)
        text = transcription["text"].strip()
        if not text:
            raise ProcessingError("No speech was detected in the recording.")

        progress = 40
        stage = "Finding decisions and action items"
        set_status(meeting_id, "ANALYSING", stage, progress)

        def on_progress(done: int, total: int):
            set_status(meeting_id, "ANALYSING", stage, 40 + int(55 * done / max(total, 1)))

        result = generate_minutes(
            text, segments=transcription.get("segments"), progress=on_progress
        )

        transcript_record = TranscriptDB(
            id=str(uuid4()),
            meeting_id=meeting_id,
            audio_id=audio.id,
            text=text,
            language=transcription.get("language"),
            segments_json=json.dumps(transcription.get("segments", []), ensure_ascii=False),
        )
        db.add(transcript_record)
        db.flush()
        db.add(
            MinutesDB(
                id=str(uuid4()),
                meeting_id=meeting_id,
                transcript_id=transcript_record.id,
                content_json=json.dumps(
                    {"format": "ui-v1", "minutes": to_ui_minutes(result, meta), "raw": result},
                    ensure_ascii=False,
                ),
            )
        )
        meeting.status = "processed"
        db.commit()
        set_status(meeting_id, "READY", "Minutes ready", 100)

    except (ProcessingError, TranscriptionError) as exc:
        db.rollback()
        set_status(meeting_id, "FAILED", "", progress, str(exc))
    except Exception:
        logger.exception("Minutes job failed for meeting %s", meeting_id)
        db.rollback()
        set_status(
            meeting_id, "FAILED", "", progress,
            "Something went wrong while generating the minutes. Please retry.",
        )
    finally:
        db.close()