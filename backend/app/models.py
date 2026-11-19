from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from app.crypto import EncryptedText
from app.database import Base


class MeetingDB(Base):
    __tablename__ = "meetings"

    id = Column(String, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, default="", nullable=False)
    status = Column(String(50), default="created", nullable=False)
    # JSON: attendees, date/time, agenda, language entered in the web form
    details_json = Column(Text, nullable=True)
    # The user who created the meeting (None for meetings created before login existed)
    owner_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class UserDB(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True)
    email = Column(String(320), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String(20), default="user", nullable=False)  # "admin" or "user"
    failed_attempts = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class TranscriptDB(Base):
    __tablename__ = "transcripts"

    id = Column(String, primary_key=True, index=True)
    meeting_id = Column(
        String,
        ForeignKey("meetings.id"),
        nullable=False,
        index=True,
    )
    audio_id = Column(String, nullable=False)
    text = Column(EncryptedText, nullable=False)          # encrypted at rest (AMG-SR-002)
    language = Column(String(20), nullable=True)
    segments_json = Column(EncryptedText, nullable=False, default="[]")
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class MinutesDB(Base):
    __tablename__ = "minutes"

    id = Column(String, primary_key=True, index=True)
    meeting_id = Column(
        String,
        ForeignKey("meetings.id"),
        nullable=False,
        index=True,
    )
    transcript_id = Column(
        String,
        ForeignKey("transcripts.id"),
        nullable=False,
    )
    content_json = Column(EncryptedText, nullable=False)  # encrypted at rest (AMG-SR-002)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class MinutesVersionDB(Base):
    """An earlier saved version of a meeting's minutes (version history, AMG-F-043)."""

    __tablename__ = "minutes_versions"

    id = Column(String, primary_key=True, index=True)
    meeting_id = Column(String, ForeignKey("meetings.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    content_json = Column(EncryptedText, nullable=False)
    saved_by = Column(String, nullable=True)  # email of the person who saved it
    saved_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SessionDB(Base):
    """A login session; refresh tokens rotate and logout revokes it (AMG-SR-004)."""

    __tablename__ = "sessions"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    refresh_hash = Column(String, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AuditDB(Base):
    """Tamper-evident audit trail: each row stores a hash that includes the previous row's hash."""

    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime(timezone=True), nullable=False)
    actor_id = Column(String, nullable=True)
    actor_email = Column(String, nullable=True)
    event = Column(String(50), nullable=False, index=True)
    detail = Column(Text, nullable=False, default="")
    prev_hash = Column(String, nullable=False)
    hash = Column(String, nullable=False)


class ReminderSentDB(Base):
    """Remembers which deadline reminders were already emailed (AMG-F-051)."""

    __tablename__ = "reminders_sent"

    id = Column(String, primary_key=True)
    meeting_id = Column(String, nullable=False, index=True)
    item_id = Column(String, nullable=False)
    due = Column(String, nullable=False)
    sent_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AudioDB(Base):
    __tablename__ = "audio_files"

    id = Column(String, primary_key=True, index=True)
    meeting_id = Column(
        String,
        ForeignKey("meetings.id"),
        nullable=False,
        index=True,
    )
    filename = Column(String, nullable=False)
    file_path = Column(Text, nullable=False)
    size_bytes = Column(Integer, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

class MeetingMetaDB(Base):
    """Extra meeting details from the frontend form, stored as JSON."""

    __tablename__ = "meeting_meta"

    meeting_id = Column(String, ForeignKey("meetings.id"), primary_key=True)
    meta_json = Column(Text, nullable=False, default="{}")