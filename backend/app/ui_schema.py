"""Shape of the minutes exchanged with the web UI (frontend/src/types.ts)."""
from typing import Literal

from pydantic import BaseModel, Field


class UIAttendee(BaseModel):
    name: str = Field(max_length=200)
    email: str = Field(default="", max_length=320)


class UITopic(BaseModel):
    id: str
    title: str = ""
    summary: str = ""


class UIDecision(BaseModel):
    id: str
    statement: str = ""
    confidence: float = 1.0


class UIActionItem(BaseModel):
    id: str
    task: str = ""
    owner: str = "Unassigned"
    due: str = ""
    status: Literal["Open", "Done"] = "Open"
    confidence: float = 1.0


class UIMinutes(BaseModel):
    version: int = 1
    title: str = ""
    datetime: str = ""
    agenda: str = ""
    attendees: list[UIAttendee] = Field(default_factory=list)
    topics: list[UITopic] = Field(default_factory=list)
    decisions: list[UIDecision] = Field(default_factory=list)
    actionItems: list[UIActionItem] = Field(default_factory=list)


class SaveMinutesRequest(BaseModel):
    content: UIMinutes


class ExportRequest(BaseModel):
    format: Literal["docx", "pdf", "md"]
    content: UIMinutes | None = None
