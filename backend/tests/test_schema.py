import pytest
from pydantic import ValidationError
from minutes import MeetingMinutes, ActionItem
from app.ui_schema import (
    UIAttendee,
    UITopic,
    UIDecision,
    UIActionItem,
    UIMinutes,
    SaveMinutesRequest,
    ExportRequest,
)
from app.database import get_db


def test_valid_minutes():
    m = MeetingMinutes(
        title="Sprint planning",
        summary="Team planned the next sprint.",
        action_items=[ActionItem(task="Write tests", owner="Asha")],
    )
    assert m.action_items[0].deadline is None
    assert m.decisions == []


def test_missing_required_field_fails():
    with pytest.raises(ValidationError):
        MeetingMinutes(summary="no title given")


def test_ui_schema_models():
    att = UIAttendee(name="Asha", email="asha@example.com")
    top = UITopic(id="t1", title="Demo", summary="Overview")
    dec = UIDecision(id="d1", statement="Approved", confidence=0.95)
    act = UIActionItem(id="a1", task="Deploy", owner="Asha", due="2026-11-20", status="Open", confidence=0.9)
    minutes = UIMinutes(
        version=1,
        title="Review",
        datetime="2026-11-19T10:00",
        agenda="Planning",
        attendees=[att],
        topics=[top],
        decisions=[dec],
        actionItems=[act],
    )
    assert minutes.title == "Review"
    assert len(minutes.actionItems) == 1

    save_req = SaveMinutesRequest(content=minutes)
    assert save_req.content.version == 1

    export_req = ExportRequest(format="docx", content=minutes)
    assert export_req.format == "docx"


def test_database_get_db_generator():
    db_gen = get_db()
    session = next(db_gen)
    assert session is not None
    try:
        next(db_gen)
    except StopIteration:
        pass
