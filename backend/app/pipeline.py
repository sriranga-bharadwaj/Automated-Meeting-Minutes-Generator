"""Background processing and minutes shaping shared by the API and the web UI.

Flow for one meeting:  audio -> transcribe_audio() -> generate_minutes() -> database.

* ``run_job`` does that work in the background and reports progress through
  ``get_job`` so the UI can poll ``GET /meetings/{id}/status``.
* ``to_ui_minutes`` converts what the minutes generator returns into the shape
  the React app edits (see ``frontend/src/types.ts``).
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
import threading
from uuid import uuid4

from app import database
from app.minutes_generator import generate_minutes
from app.models import AudioDB, MeetingDB, MinutesDB, TranscriptDB
from app.transcription import TranscriptionError, transcribe_audio

logger = logging.getLogger(__name__)

# Whisper and the local LLM are CPU heavy: process one meeting at a time.
_PROCESS_LOCK = threading.Lock()
_JOBS: dict[str, dict] = {}
_JOBS_LOCK = threading.Lock()


# --------------------------------------------------------------------------
# Job state
# --------------------------------------------------------------------------
def set_job(meeting_id: str, status: str, progress: int, stage: str = "", error: str | None = None):
    with _JOBS_LOCK:
        _JOBS[meeting_id] = {
            "status": status,
            "progress": progress,
            "stage": stage,
            "error": error,
        }


def get_job(meeting_id: str) -> dict | None:
    with _JOBS_LOCK:
        job = _JOBS.get(meeting_id)
        return dict(job) if job else None


def is_running(meeting_id: str) -> bool:
    job = get_job(meeting_id)
    return bool(job and job["status"] in {"QUEUED", "TRANSCRIBING", "ANALYSING"})


def status_for(meeting: MeetingDB) -> dict:
    """Current job status, falling back to what the database knows (e.g. after a restart)."""
    job = get_job(meeting.id)
    if job:
        return job
    if meeting.status == "processed":
        return {"status": "READY", "progress": 100, "stage": "Minutes ready", "error": None}
    if meeting.status == "processing":
        return {
            "status": "FAILED",
            "progress": 0,
            "stage": "",
            "error": "Processing was interrupted. Press Retry to start again.",
        }
    if meeting.status == "failed":
        return {"status": "FAILED", "progress": 0, "stage": "", "error": "Processing failed. Press Retry."}
    return {"status": "QUEUED", "progress": 0, "stage": "Waiting to start", "error": None}


# --------------------------------------------------------------------------
# Saving results
# --------------------------------------------------------------------------
def persist_result(db, meeting: MeetingDB, audio: AudioDB, transcription: dict, minutes: dict):
    """Store transcript + minutes for a meeting and mark it processed. Caller commits."""
    transcript_record = TranscriptDB(
        id=str(uuid4()),
        meeting_id=meeting.id,
        audio_id=audio.id,
        text=transcription["text"].strip(),
        language=transcription.get("language"),
        segments_json=json.dumps(transcription.get("segments", []), ensure_ascii=False),
    )
    db.add(transcript_record)
    db.flush()

    minutes_record = MinutesDB(
        id=str(uuid4()),
        meeting_id=meeting.id,
        transcript_id=transcript_record.id,
        content_json=json.dumps(minutes, ensure_ascii=False),
    )
    db.add(minutes_record)
    meeting.status = "processed"
    return transcript_record, minutes_record


def friendly_error(exc: Exception) -> str:
    if isinstance(exc, (TranscriptionError, FileNotFoundError, ValueError)):
        return str(exc)
    return "Something went wrong while processing the recording. Please try again."


def run_job(meeting_id: str):
    """Transcribe the latest audio of a meeting and generate its minutes."""
    set_job(meeting_id, "QUEUED", 5, "Waiting for a free worker")
    with _PROCESS_LOCK:
        db = database.SessionLocal()
        try:
            meeting = db.query(MeetingDB).filter(MeetingDB.id == meeting_id).first()
            audio = (
                db.query(AudioDB)
                .filter(AudioDB.meeting_id == meeting_id)
                .order_by(AudioDB.created_at.desc())
                .first()
            )
            if meeting is None or audio is None:
                raise ValueError("No audio found for this meeting.")

            meeting.status = "processing"
            db.commit()

            details = load_details(meeting)
            set_job(meeting_id, "TRANSCRIBING", 20, "Converting speech to text")
            transcription = transcribe_audio(audio.file_path, language=details.get("language") or None)

            if not transcription["text"].strip():
                raise ValueError("No speech was detected in the audio.")

            set_job(meeting_id, "ANALYSING", 60, "Finding decisions and action items")
            minutes = generate_minutes(
                transcription["text"].strip(),
                segments=transcription.get("segments"),
            )

            persist_result(db, meeting, audio, transcription, minutes)
            db.commit()
            set_job(meeting_id, "READY", 100, "Minutes ready")
        except Exception as exc:  # noqa: BLE001 - reported to the UI
            db.rollback()
            logger.exception("Processing failed for meeting %s", meeting_id)
            try:
                meeting = db.query(MeetingDB).filter(MeetingDB.id == meeting_id).first()
                if meeting is not None:
                    meeting.status = "failed"
                    db.commit()
            except Exception:  # noqa: BLE001
                db.rollback()
            set_job(meeting_id, "FAILED", 0, "", friendly_error(exc))
        finally:
            db.close()


# --------------------------------------------------------------------------
# Minutes for the UI
# --------------------------------------------------------------------------
def load_details(meeting: MeetingDB) -> dict:
    try:
        return json.loads(meeting.details_json) if meeting.details_json else {}
    except json.JSONDecodeError:
        return {}


def _new_id() -> str:
    return uuid4().hex[:8]


_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_MONTHS = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]


def resolve_deadline(text: str | None, meeting_date: str = "") -> str:
    """Turn a spoken deadline ("Wednesday", "tomorrow", "Nov 4") into yyyy-mm-dd, or '' if unclear."""
    if not text:
        return ""
    t = text.strip().lower()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t):
        return t
    try:
        base = dt.date.fromisoformat(meeting_date[:10]) if meeting_date else dt.date.today()
    except ValueError:
        base = dt.date.today()

    if re.search(r"\btoday\b", t):
        return base.isoformat()
    if re.search(r"\btomorrow\b", t):
        return (base + dt.timedelta(days=1)).isoformat()
    for i, day in enumerate(_WEEKDAYS):
        if re.search(rf"\b{day}\b", t):
            ahead = (i - base.weekday()) % 7 or 7
            return (base + dt.timedelta(days=ahead)).isoformat()
    m = re.search(r"\b(" + "|".join(mn[:3] for mn in _MONTHS) + r")[a-z]*\.?\s+(\d{1,2})\b", t)
    if m:
        month = [mn[:3] for mn in _MONTHS].index(m.group(1)) + 1
        try:
            day = dt.date(base.year, month, int(m.group(2)))
            if day < base:
                day = dt.date(base.year + 1, month, int(m.group(2)))
            return day.isoformat()
        except ValueError:
            return ""
    return ""


def guess_owner(sentence: str, attendees: list[dict]) -> str | None:
    """For the keyword fallback: the attendee named first in the sentence, if any."""
    best, best_pos = None, None
    for person in attendees:
        name = (person.get("name") or "").strip()
        if not name:
            continue
        for token in {name, name.split()[0]}:
            m = re.search(rf"\b{re.escape(token)}\b", sentence, re.IGNORECASE)
            if m and (best_pos is None or m.start() < best_pos):
                best, best_pos = name, m.start()
    return best


def to_ui_minutes(raw: dict, meeting: MeetingDB, version: int = 1) -> dict:
    """Convert generator output (or an already-edited UI version) to the UI shape."""
    if "actionItems" in raw:  # saved from the UI editor
        return {**raw, "version": version}

    details = load_details(meeting)
    when = details.get("datetime", "")
    engine = raw.get("engine", "basic")
    confidence = 1.0 if engine == "llm" else 0.5  # keyword guesses are flagged for review

    form_attendees = details.get("attendees") or []

    if engine == "llm":
        topics = [
            {"id": _new_id(), "title": t.get("title", ""), "summary": t.get("summary", "")}
            for t in raw.get("topics", [])
        ]
        decisions = [d.get("decision", "") for d in raw.get("decision_details", [])]
        actions = raw.get("action_item_details", [])
    else:
        topics = [
            {"id": _new_id(), "title": f"Point {i}", "summary": s}
            for i, s in enumerate(raw.get("key_discussions", [])[:5], start=1)
        ]
        decisions = list(raw.get("decisions", []))
        actions = [
            {
                "task": s,
                "owner": guess_owner(s, form_attendees),
                "deadline": resolve_deadline(s, when) or None,
            }
            for s in raw.get("action_items", [])
        ]

    action_items = []
    for a in actions:
        task = a.get("task", "")
        due = resolve_deadline(a.get("deadline"), when)
        if a.get("deadline") and not due:
            task = f"{task} (deadline: {a['deadline']})"
        action_items.append(
            {
                "id": _new_id(),
                "task": task,
                "owner": a.get("owner") or "Unassigned",
                "due": due,
                "status": "Open",
                "confidence": confidence,
            }
        )

    attendees = details.get("attendees") or [
        {"name": n, "email": ""} for n in raw.get("participants", [])
    ]
    return {
        "version": version,
        "title": raw.get("title") or meeting.title,
        "datetime": when,
        "agenda": details.get("agenda", ""),
        "attendees": attendees,
        "topics": topics,
        "decisions": [{"id": _new_id(), "statement": s, "confidence": confidence} for s in decisions],
        "actionItems": action_items,
    }


def latest_minutes_row(db, meeting_id: str) -> MinutesDB | None:
    return (
        db.query(MinutesDB)
        .filter(MinutesDB.meeting_id == meeting_id)
        .order_by(MinutesDB.created_at.desc(), MinutesDB.id.desc())
        .first()
    )


def current_ui_minutes(db, meeting: MeetingDB) -> tuple[dict, MinutesDB] | None:
    row = latest_minutes_row(db, meeting.id)
    if row is None:
        return None
    raw = json.loads(row.content_json)
    version = int(raw.get("version", 1)) if "actionItems" in raw else 1
    return to_ui_minutes(raw, meeting, version), row
