from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base
from app.database import Base


class MeetingDB(Base):
    __tablename__ = "meetings"

    id = Column(String, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, default="", nullable=False)
    status = Column(String(50), default="created", nullable=False)
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
    text = Column(Text, nullable=False)
    language = Column(String(20), nullable=True)
    segments_json = Column(Text, nullable=False, default="[]")
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
    content_json = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


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
