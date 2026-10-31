from typing import Optional
from pydantic import BaseModel, Field


class Topic(BaseModel):
    title: str
    summary: str
    start_time: Optional[float] = None   # seconds, if timestamps exist


class Decision(BaseModel):
    decision: str
    context: Optional[str] = None


class ActionItem(BaseModel):
    task: str
    owner: Optional[str] = None      # None if nobody was assigned
    deadline: Optional[str] = None   # free text, e.g. "next Friday"


class MeetingMinutes(BaseModel):
    title: str
    summary: str
    participants: list[str] = Field(default_factory=list)
    topics: list[Topic] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)