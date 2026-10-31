import pytest
from pydantic import ValidationError
from minutes import MeetingMinutes, ActionItem


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