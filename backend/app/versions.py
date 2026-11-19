"""Version history of a meeting's minutes (AMG-F-043).

Every time minutes are saved, the version being replaced is copied into ``minutes_versions``,
so earlier versions can be listed, read and restored.
"""
import json
from typing import Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models import MinutesVersionDB


def archive(db: Session, meeting_id: str, minutes: dict, version: int, saved_by: Optional[str]) -> None:
    """Keep ``minutes`` as version ``version``. The caller commits."""
    already = (
        db.query(MinutesVersionDB)
        .filter(MinutesVersionDB.meeting_id == meeting_id, MinutesVersionDB.version == version)
        .first()
    )
    if already is not None:
        return
    db.add(
        MinutesVersionDB(
            id=str(uuid4()),
            meeting_id=meeting_id,
            version=version,
            content_json=json.dumps(minutes, ensure_ascii=False),
            saved_by=saved_by,
        )
    )


def list_versions(db: Session, meeting_id: str) -> list[dict]:
    rows = (
        db.query(MinutesVersionDB)
        .filter(MinutesVersionDB.meeting_id == meeting_id)
        .order_by(MinutesVersionDB.version.desc())
        .all()
    )
    return [
        {"version": r.version, "saved_at": r.saved_at.isoformat() if r.saved_at else None, "saved_by": r.saved_by}
        for r in rows
    ]


def get_version(db: Session, meeting_id: str, version: int) -> Optional[dict]:
    row = (
        db.query(MinutesVersionDB)
        .filter(MinutesVersionDB.meeting_id == meeting_id, MinutesVersionDB.version == version)
        .first()
    )
    return json.loads(row.content_json) if row else None
