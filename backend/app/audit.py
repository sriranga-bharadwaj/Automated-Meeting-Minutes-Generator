"""Tamper-evident audit log (AMG-SR-008).

Login, logout, share, export, delete, role-change and similar events are written to the
``audit_log`` table. Every row stores a SHA-256 hash of its own content plus the previous
row's hash, so editing or deleting a row in the middle breaks the chain and ``verify_chain``
reports where. Rows older than one year are removed by ``purge_old``.
"""
import hashlib
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models import AuditDB

RETENTION_DAYS = 365
GENESIS = "0" * 64
_lock = threading.Lock()


def _stamp(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%S.%f")


def _digest(prev_hash: str, ts: datetime, actor_id: Optional[str], event: str, detail: str) -> str:
    text = "|".join([prev_hash, _stamp(ts), actor_id or "", event, detail])
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def log(db: Session, event: str, actor: Optional[dict] = None, detail: str = "") -> None:
    """Append an event. ``actor`` is request.state.user ({id, email, ...}) or None."""
    with _lock:
        last = db.query(AuditDB).order_by(AuditDB.id.desc()).first()
        prev_hash = last.hash if last else GENESIS
        ts = datetime.now(timezone.utc).replace(tzinfo=None)
        actor_id = actor["id"] if actor else None
        db.add(
            AuditDB(
                ts=ts,
                actor_id=actor_id,
                actor_email=actor["email"] if actor else None,
                event=event,
                detail=detail,
                prev_hash=prev_hash,
                hash=_digest(prev_hash, ts, actor_id, event, detail),
            )
        )
        db.commit()


def verify_chain(db: Session) -> tuple[bool, Optional[int]]:
    """(True, None) when every row is intact, else (False, id of the first bad row)."""
    expected_prev = None
    for row in db.query(AuditDB).order_by(AuditDB.id).all():
        if expected_prev is not None and row.prev_hash != expected_prev:
            return False, row.id
        if row.hash != _digest(row.prev_hash, row.ts, row.actor_id, row.event, row.detail):
            return False, row.id
        expected_prev = row.hash
    return True, None


def purge_old(db: Session, days: int = RETENTION_DAYS) -> int:
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    count = db.query(AuditDB).filter(AuditDB.ts < cutoff).delete()
    db.commit()
    return count
