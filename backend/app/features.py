"""Transcript editing and playback, version history, sharing, action tracker, reminders,
retention and the admin console.

Requirements covered: AMG-F-022 (edit transcript), AMG-F-042 (source links), AMG-F-043 (version
history), AMG-F-045 (share by email), AMG-F-050 (action dashboard), AMG-F-051 (reminders and
status), AMG-F-060 (job monitoring), AMG-F-061 (retention), AMG-SR-008 (audit log views).

The routes are mounted at the root and under /api/v1. Login and ownership checks come from
AuthMiddleware (app/auth.py); the admin routes sit under /admin/ which only administrators reach.
"""
import json
import logging
import mimetypes
import os
import shutil
import tempfile
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app import audit, auth, crypto, database, export, mailer, pipeline, security, sources, versions
from app.database import get_db
from app.models import (
    AudioDB, MeetingDB, MeetingMetaDB, MinutesDB, ReminderSentDB, TranscriptDB, UserDB,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["features"])


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"code": code, "message": message, "detail": message})


# ====================================================================== shared helpers
def _meeting_or_404(db: Session, meeting_id: str) -> MeetingDB:
    meeting = db.query(MeetingDB).filter(MeetingDB.id == meeting_id).first()
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found.")
    return meeting


def latest_transcript(db: Session, meeting_id: str) -> Optional[TranscriptDB]:
    return (
        db.query(TranscriptDB)
        .filter(TranscriptDB.meeting_id == meeting_id)
        .order_by(TranscriptDB.created_at.desc(), TranscriptDB.id.desc())
        .first()
    )


def segments_for(db: Session, meeting_id: str) -> list[dict]:
    transcript = latest_transcript(db, meeting_id)
    if transcript is None:
        return []
    try:
        return json.loads(transcript.segments_json or "[]")
    except json.JSONDecodeError:
        return []


def _latest_minutes_row(db: Session, meeting_id: str) -> Optional[MinutesDB]:
    return (
        db.query(MinutesDB)
        .filter(MinutesDB.meeting_id == meeting_id)
        .order_by(MinutesDB.created_at.desc(), MinutesDB.id.desc())
        .first()
    )


def ui_minutes(db: Session, meeting: MeetingDB) -> Optional[tuple[dict, MinutesDB]]:
    """The minutes in the shape the web UI uses, whichever route created them."""
    row = _latest_minutes_row(db, meeting.id)
    if row is None:
        return None
    raw = json.loads(row.content_json)
    if raw.get("format") == "ui-v1":          # written by the /api/v1 routes
        return raw["minutes"], row
    minutes = pipeline.to_ui_minutes(raw, meeting, int(raw.get("version", 1)) if "actionItems" in raw else 1)
    if "actionItems" not in raw:
        _stable_ids(minutes, meeting.id)
    return minutes, row


def _stable_ids(minutes: dict, meeting_id: str) -> None:
    """Minutes that were never saved get new random item ids on every conversion; give them ids
    derived from their content so the action tracker can refer to the same item twice."""
    import hashlib

    for kind, field in (("topics", "title"), ("decisions", "statement"), ("actionItems", "task")):
        for index, item in enumerate(minutes.get(kind, [])):
            seed = f"{meeting_id}|{kind}|{index}|{item.get(field, '')}"
            item["id"] = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8]


def write_ui_minutes(row: MinutesDB, minutes: dict) -> None:
    raw = json.loads(row.content_json)
    if raw.get("format") == "ui-v1":
        raw["minutes"] = minutes
        row.content_json = json.dumps(raw, ensure_ascii=False)
    else:
        row.content_json = json.dumps(minutes, ensure_ascii=False)


def attendees_of(db: Session, meeting: MeetingDB) -> list[dict]:
    details = pipeline.load_details(meeting)
    if details.get("attendees"):
        return details["attendees"]
    meta = db.query(MeetingMetaDB).filter(MeetingMetaDB.meeting_id == meeting.id).first()
    try:
        return json.loads(meta.meta_json).get("attendees", []) if meta else []
    except json.JSONDecodeError:
        return []


def email_for_owner(owner: str, attendees: list[dict]) -> Optional[str]:
    low = owner.strip().lower()
    for person in attendees:
        name = (person.get("name") or "").strip().lower()
        if person.get("email") and name and (name == low or name.split()[0] == low):
            return person["email"]
    return None


def _save_new_version(db: Session, meeting: MeetingDB, row: MinutesDB, current: dict, minutes: dict, user) -> int:
    """Archive ``current`` and store ``minutes`` as the next version. The caller commits."""
    new_version = int(current.get("version", 1)) + 1
    versions.archive(db, meeting.id, current, int(current.get("version", 1)), user["email"] if user else None)
    minutes = {**minutes, "version": new_version}
    write_ui_minutes(row, minutes)
    return new_version


# ====================================================================== transcript (AMG-F-022)
class SegmentIn(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str = Field(max_length=5000)
    speaker: str = Field(default="", max_length=100)


class TranscriptIn(BaseModel):
    segments: list[SegmentIn] = Field(max_length=5000)


@router.get("/meetings/{meeting_id}/transcript")
def get_transcript(meeting_id: str, db: Session = Depends(get_db)):
    _meeting_or_404(db, meeting_id)
    transcript = latest_transcript(db, meeting_id)
    if transcript is None:
        raise HTTPException(status_code=404, detail="There is no transcript yet.")
    segments = [{"speaker": "", **s} for s in segments_for(db, meeting_id)]
    return {"language": transcript.language, "text": transcript.text, "segments": segments}


@router.put("/meetings/{meeting_id}/transcript")
def put_transcript(meeting_id: str, body: TranscriptIn, request: Request, db: Session = Depends(get_db)):
    """Save edited segment text and speaker labels."""
    _meeting_or_404(db, meeting_id)
    transcript = latest_transcript(db, meeting_id)
    if transcript is None:
        raise HTTPException(status_code=404, detail="There is no transcript yet.")
    segments = [
        {
            "start": round(s.start, 2),
            "end": round(max(s.end, s.start), 2),
            "text": security.sanitize_text(s.text).strip(),
            "speaker": security.sanitize_text(s.speaker).strip(),
        }
        for s in body.segments
    ]
    transcript.segments_json = json.dumps(segments, ensure_ascii=False)
    transcript.text = " ".join(s["text"] for s in segments if s["text"])
    db.commit()
    audit.log(db, "transcript-edit", auth.current_user(request), meeting_id)
    return {"segments": len(segments)}


@router.get("/meetings/{meeting_id}/audio/stream")
def stream_audio(meeting_id: str, db: Session = Depends(get_db)):
    """The recording, decrypted for playback next to the transcript."""
    _meeting_or_404(db, meeting_id)
    audio = (
        db.query(AudioDB)
        .filter(AudioDB.meeting_id == meeting_id)
        .order_by(AudioDB.created_at.desc())
        .first()
    )
    if audio is None or not Path(audio.file_path).is_file():
        raise HTTPException(status_code=404, detail="No recording was found for this meeting.")
    media_type = mimetypes.guess_type(audio.filename)[0] or "application/octet-stream"
    if not crypto.is_encrypted_file(audio.file_path):
        return FileResponse(audio.file_path, media_type=media_type)
    tmp_dir = tempfile.mkdtemp(prefix="ammg_play_")
    plain = Path(tmp_dir) / Path(audio.file_path).name
    crypto.decrypt_file_to(audio.file_path, plain)
    return FileResponse(plain, media_type=media_type, background=BackgroundTask(shutil.rmtree, tmp_dir, True))


# ====================================================================== sources and versions
@router.get("/meetings/{meeting_id}/minutes/with-sources")
def minutes_with_sources(meeting_id: str, db: Session = Depends(get_db)):
    """The minutes with a ``source`` (seconds in the recording) on every item that can be linked."""
    meeting = _meeting_or_404(db, meeting_id)
    found = ui_minutes(db, meeting)
    if found is None:
        raise HTTPException(status_code=404, detail="Minutes have not been generated yet.")
    return sources.attach(found[0], segments_for(db, meeting_id))


@router.get("/meetings/{meeting_id}/minutes/versions")
def list_versions(meeting_id: str, db: Session = Depends(get_db)):
    meeting = _meeting_or_404(db, meeting_id)
    found = ui_minutes(db, meeting)
    if found is None:
        raise HTTPException(status_code=404, detail="Minutes have not been generated yet.")
    current = int(found[0].get("version", 1))
    older = versions.list_versions(db, meeting_id)
    return [{"version": current, "saved_at": None, "saved_by": None, "current": True}] + [
        {**v, "current": False} for v in older if v["version"] != current
    ]


@router.get("/meetings/{meeting_id}/minutes/versions/{version}")
def get_version(meeting_id: str, version: int, db: Session = Depends(get_db)):
    meeting = _meeting_or_404(db, meeting_id)
    found = ui_minutes(db, meeting)
    if found is not None and int(found[0].get("version", 1)) == version:
        return found[0]
    old = versions.get_version(db, meeting_id, version)
    if old is None:
        raise HTTPException(status_code=404, detail="That version does not exist.")
    return old


@router.post("/meetings/{meeting_id}/minutes/versions/{version}/restore")
def restore_version(meeting_id: str, version: int, request: Request, db: Session = Depends(get_db)):
    """Make an earlier version the newest one (it is saved as a new version; nothing is lost)."""
    meeting = _meeting_or_404(db, meeting_id)
    found = ui_minutes(db, meeting)
    if found is None:
        raise HTTPException(status_code=404, detail="Minutes have not been generated yet.")
    current, row = found
    old = versions.get_version(db, meeting_id, version)
    if old is None:
        raise HTTPException(status_code=404, detail="That version does not exist.")
    user = auth.current_user(request)
    new_version = _save_new_version(db, meeting, row, current, old, user)
    db.commit()
    audit.log(db, "minutes-restore", user, f"{meeting_id}: v{version} -> v{new_version}")
    return {"version": new_version}


# ====================================================================== share by email (AMG-F-045)
class ShareIn(BaseModel):
    emails: list[str] = Field(min_length=1, max_length=20)
    format: str = "pdf"


@router.post("/meetings/{meeting_id}/share")
def share_minutes(meeting_id: str, body: ShareIn, request: Request, db: Session = Depends(get_db)):
    meeting = _meeting_or_404(db, meeting_id)
    emails = [e.strip() for e in body.emails if e.strip()]
    if not emails or any(not auth.EMAIL_RE.match(e) for e in emails):
        return _error(400, "INVALID", "Enter valid email addresses, separated by commas.")
    if body.format not in {"docx", "pdf", "md"}:
        return _error(400, "INVALID", "The format must be docx, pdf or md.")
    found = ui_minutes(db, meeting)
    if found is None:
        return _error(404, "NOT_READY", "Minutes have not been generated yet.")
    data, media_type, filename = export.render(found[0], body.format)
    try:
        mailer.send(
            emails,
            f"Meeting minutes: {meeting.title}",
            f"Hello,\n\nThe minutes of \"{meeting.title}\" are attached.\n",
            (data, media_type, filename),
        )
    except mailer.MailError as exc:
        return _error(502, "MAIL_FAILED", str(exc))
    audit.log(db, "share", auth.current_user(request), f"{meeting_id} to {len(emails)} address(es) as {body.format}")
    return {"sent": len(emails)}


# ====================================================================== action tracker (AMG-F-050/051)
class ActionStatusIn(BaseModel):
    status: str


def _accessible_meetings(db: Session, user: Optional[dict]) -> list[tuple[MeetingDB, bool]]:
    """(meeting, can_edit): the meetings a person owns (editable) and was invited to (read only)."""
    out = []
    for meeting in db.query(MeetingDB).order_by(MeetingDB.created_at.desc()).all():
        editable = user is None or user["role"] == "admin" or meeting.owner_id == user["id"]
        if editable or auth.is_invited(db, meeting, user["email"]):
            out.append((meeting, editable))
    return out


@router.get("/actions")
def list_actions(
    request: Request,
    status: str = "",
    owner: str = "",
    overdue: bool = False,
    db: Session = Depends(get_db),
):
    """Action items from the latest minutes of every meeting the person may see."""
    today = date.today().isoformat()
    rows = []
    for meeting, can_edit in _accessible_meetings(db, auth.current_user(request)):
        found = ui_minutes(db, meeting)
        if found is None:
            continue
        for item in found[0].get("actionItems", []):
            is_overdue = item.get("status") != "Done" and bool(item.get("due")) and item["due"] < today
            rows.append(
                {
                    "meeting_id": meeting.id,
                    "meeting_title": meeting.title,
                    "id": item.get("id"),
                    "task": item.get("task", ""),
                    "owner": item.get("owner", "Unassigned"),
                    "due": item.get("due", ""),
                    "status": item.get("status", "Open"),
                    "overdue": is_overdue,
                    "can_edit": can_edit,
                }
            )
    if status:
        rows = [r for r in rows if r["status"].lower() == status.lower()]
    if owner:
        rows = [r for r in rows if owner.lower() in r["owner"].lower()]
    if overdue:
        rows = [r for r in rows if r["overdue"]]
    # Open items with the earliest deadline first; items without a date last.
    rows.sort(key=lambda r: (r["status"] == "Done", r["due"] == "", r["due"]))
    return rows


@router.patch("/meetings/{meeting_id}/actions/{item_id}")
def set_action_status(
    meeting_id: str, item_id: str, body: ActionStatusIn, request: Request, db: Session = Depends(get_db)
):
    """Mark an action item Open or Done (saved as a new version of the minutes)."""
    if body.status not in {"Open", "Done"}:
        return _error(400, "INVALID", "The status must be Open or Done.")
    meeting = _meeting_or_404(db, meeting_id)
    found = ui_minutes(db, meeting)
    if found is None:
        return _error(404, "NOT_READY", "Minutes have not been generated yet.")
    current, row = found
    if not any(a.get("id") == item_id for a in current.get("actionItems", [])):
        return _error(404, "NOT_FOUND", "That action item does not exist.")
    updated = {
        **current,
        "actionItems": [
            {**a, "status": body.status} if a.get("id") == item_id else a for a in current["actionItems"]
        ],
    }
    new_version = _save_new_version(db, meeting, row, current, updated, auth.current_user(request))
    db.commit()
    return {"version": new_version, "status": body.status}


# ====================================================================== reminders (AMG-F-051)
def run_reminders(db: Session, today: Optional[date] = None, within_days: int = 1, send=None) -> dict:
    """Email each owner of an open action item due within ``within_days`` (or overdue), once."""
    send = send or mailer.send
    today = today or date.today()
    limit = (today + timedelta(days=within_days)).isoformat()
    sent = skipped = failed = 0
    for meeting in db.query(MeetingDB).all():
        found = ui_minutes(db, meeting)
        if found is None:
            continue
        people = attendees_of(db, meeting)
        for item in found[0].get("actionItems", []):
            due = item.get("due") or ""
            if item.get("status") == "Done" or not due or due > limit:
                continue
            already = (
                db.query(ReminderSentDB)
                .filter(
                    ReminderSentDB.meeting_id == meeting.id,
                    ReminderSentDB.item_id == str(item.get("id")),
                    ReminderSentDB.due == due,
                )
                .first()
            )
            email = email_for_owner(item.get("owner", ""), people)
            if already is not None or email is None:
                skipped += 1
                continue
            when = "is overdue" if due < today.isoformat() else f"is due on {due}"
            try:
                send(
                    [email],
                    f"Reminder: {item.get('task', '')[:80]}",
                    f"Hello {item.get('owner')},\n\nThe action item \"{item.get('task')}\" from the meeting "
                    f"\"{meeting.title}\" {when}.\n",
                )
            except mailer.MailError as exc:
                logger.warning("Reminder not sent: %s", exc)
                failed += 1
                continue
            db.add(ReminderSentDB(id=str(uuid4()), meeting_id=meeting.id, item_id=str(item.get("id")), due=due))
            db.commit()
            sent += 1
    return {"sent": sent, "skipped": skipped, "failed": failed}


# ====================================================================== retention (AMG-F-061)
def purge_old_meetings(db: Session, days: int) -> int:
    """Delete meetings (and their audio) created more than ``days`` days ago."""
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    count = 0
    for meeting in db.query(MeetingDB).all():
        created = meeting.created_at.replace(tzinfo=None) if meeting.created_at else None
        if created is not None and created < cutoff:
            auth.delete_meeting_data(db, meeting)
            count += 1
    return count


def start_scheduler(interval_seconds: int = 3600) -> Optional[threading.Thread]:
    """Hourly background loop: deadline reminders, retention purge and audit-log purge."""
    if os.getenv("BACKGROUND_TASKS", "true").strip().lower() in {"0", "false", "no", "off"}:
        return None

    def loop() -> None:
        while True:
            db = database.SessionLocal()
            try:
                if mailer.configured():
                    run_reminders(db)
                days = int(os.getenv("RETENTION_DAYS", "0") or 0)
                if days > 0 and purge_old_meetings(db, days):
                    audit.log(db, "retention-purge", None, f"older than {days} days")
                audit.purge_old(db)
            except Exception:  # noqa: BLE001 - keep the loop alive
                logger.exception("Background task failed")
            finally:
                db.close()
            time.sleep(interval_seconds)

    thread = threading.Thread(target=loop, name="ammg-background", daemon=True)
    thread.start()
    return thread


# ====================================================================== admin console (AMG-F-060, SR-008)
@router.get("/admin/jobs")
def admin_jobs(db: Session = Depends(get_db)):
    """Recent processing jobs with their live status."""
    emails = {u.id: u.email for u in db.query(UserDB).all()}
    out = []
    for meeting in db.query(MeetingDB).order_by(MeetingDB.created_at.desc()).limit(50).all():
        job = pipeline.status_for(meeting)
        audio = (
            db.query(AudioDB).filter(AudioDB.meeting_id == meeting.id).order_by(AudioDB.created_at.desc()).first()
        )
        out.append(
            {
                "meeting_id": meeting.id,
                "title": meeting.title,
                "owner_email": emails.get(meeting.owner_id),
                "status": job["status"],
                "progress": job["progress"],
                "error": job.get("error"),
                "audio_file": audio.filename if audio else None,
                "audio_bytes": audio.size_bytes if audio else None,
                "created_at": meeting.created_at.isoformat() if meeting.created_at else None,
            }
        )
    return out


@router.get("/admin/audit")
def admin_audit(limit: int = 100, db: Session = Depends(get_db)):
    from app.models import AuditDB

    rows = db.query(AuditDB).order_by(AuditDB.id.desc()).limit(max(1, min(limit, 500))).all()
    return [
        {
            "id": r.id,
            "ts": r.ts.isoformat() if r.ts else None,
            "actor": r.actor_email,
            "event": r.event,
            "detail": r.detail,
        }
        for r in rows
    ]


@router.get("/admin/audit/verify")
def admin_audit_verify(db: Session = Depends(get_db)):
    ok, bad_id = audit.verify_chain(db)
    return {"intact": ok, "first_bad_id": bad_id}


@router.post("/admin/reminders/run")
def admin_run_reminders(db: Session = Depends(get_db)):
    if not mailer.configured():
        return _error(502, "MAIL_FAILED", "Email is not set up on the server (SMTP_HOST is missing).")
    return run_reminders(db)


@router.post("/admin/retention/run")
def admin_run_retention(request: Request, days: int = 0, db: Session = Depends(get_db)):
    days = days or int(os.getenv("RETENTION_DAYS", "0") or 0)
    if days <= 0:
        return _error(400, "INVALID", "Give a number of days, or set RETENTION_DAYS on the server.")
    removed = purge_old_meetings(db, days)
    audit.log(db, "retention-purge", auth.current_user(request), f"{removed} meeting(s) older than {days} days")
    return {"removed": removed, "days": days}
